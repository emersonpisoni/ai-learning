"""
Prompts: como o jogo vira texto para o LLM.

Tudo aqui é montado a partir da PlayerView, ou seja, só com o que AQUELE
jogador pode saber. Cuidado especial com o campo `thought` dos eventos: o
agente só pode ver os PRÓPRIOS pensamentos, nunca os dos outros.
"""

from __future__ import annotations

from .engine import Event, EventKind, PlayerView, Role
from .llm import ToolSpec

NOBODY = "ninguem"

RULES = """\
Você está jogando Lobisomem, um jogo de dedução social, numa aldeia com outros jogadores.

Papéis:
- Lobisomem: à noite, os lobos escolhem juntos um jogador para matar. De dia, fingem ser aldeões. Os lobos sabem quem são os outros lobos.
- Vidente: a cada noite, descobre se um jogador é lobisomem ou não.
- Médico: a cada noite, protege um jogador (pode ser ele mesmo) do ataque dos lobos.
- Aldeão: não tem poder especial. Precisa deduzir quem são os lobos pela conversa.

Cada rodada tem: noite (ações secretas), discussão (cada jogador fala uma vez) e votação (o mais votado é eliminado; empate não elimina ninguém).
A aldeia vence se eliminar todos os lobos. Os lobos vencem quando forem pelo menos metade dos vivos.

Como jogar bem:
- Você é um jogador de verdade, não um narrador. Fale em primeira pessoa, em português do Brasil, de forma natural e curta (1 a 3 frases).
- Use o que aconteceu na partida: quem acusou quem, quem votou em quem, quem morreu e qual era o papel.
- Se for lobo, minta de forma convincente e nunca revele sua identidade ou a dos aliados.
- Se for da aldeia, desconfie com base em evidências, não em sorte.
- Discussão boa é discussão concreta. Ficar só pedindo "calma" e "provas" não ajuda ninguém e deixa os lobos livres.
- Só cite fatos que estão no histórico. Nunca invente acontecimentos.
- O que aparece no histórico como [secreto] só você (e seus aliados) sabe. Nunca diga isso em voz alta por descuido: revelar um segredo só faz sentido como estratégia consciente (por exemplo, a vidente anunciando o que descobriu).
- Sempre responda chamando a ferramenta pedida. O campo "pensamento" é privado: ninguém além de você o verá.
"""

PERSONALITIES = [
    "Desconfiada e direta: acusa sem rodeios e cobra explicações.",
    "Calma e analítica: fala pouco, mas sempre com uma lógica clara.",
    "Dramática e emotiva: exagera nas reações e se ofende fácil.",
    "Brincalhona: faz piadas, mas presta atenção em tudo.",
    "Insegura: hesita, muda de opinião e pede a opinião dos outros.",
    "Líder nata: tenta organizar a votação e convencer o grupo.",
    "Quieta e observadora: só fala quando tem certeza de algo.",
    "Teimosa: escolhe um suspeito cedo e dificilmente muda de ideia.",
    "Diplomática: tenta acalmar os ânimos e evitar acusações injustas.",
    "Cética: duvida de todo mundo, inclusive de quem diz ser vidente.",
    "Falante: comenta tudo o que aconteceu e faz muitas perguntas.",
    "Estrategista fria: pensa em probabilidades e em quem ganha com cada voto.",
]


# --------------------------------------------------------------------------- #
# System prompt: regras + papel secreto + personalidade
# --------------------------------------------------------------------------- #


def build_system(view: PlayerView, personality: str) -> str:
    lines = [RULES, f"Seu nome é {view.me}. Seu papel secreto é: {view.role.label}."]
    if view.role is Role.WEREWOLF:
        if view.allies:
            lines.append(f"Seus aliados lobisomens são: {', '.join(view.allies)}. Protejam uns aos outros.")
        else:
            lines.append("Você é o único lobisomem.")
    if personality:
        lines.append(f"Sua personalidade: {personality}")
    return "\n\n".join(lines)


# --------------------------------------------------------------------------- #
# Histórico: os eventos que este jogador viu, em texto
# --------------------------------------------------------------------------- #


def _render_event(event: Event, me: str) -> str | None:
    if event.kind is EventKind.PHASE:
        return f"\n{event.content}"
    if event.kind is EventKind.SPEECH:
        text = f'{event.actor}: "{event.content}"'
    else:
        text = event.content
    if event.visibility != "public":
        text = f"[secreto] {text}"
    # Só os PRÓPRIOS pensamentos entram no prompt.
    if event.actor == me and event.thought:
        text += f"  (seu pensamento na hora: {event.thought})"
    return text


def build_history(view: PlayerView) -> str:
    lines = [line for e in view.events if (line := _render_event(e, view.me)) is not None]
    return "\n".join(lines).strip() or "(a partida acabou de começar)"


def _situation(view: PlayerView, task: str) -> str:
    return (
        f"## O que aconteceu até agora\n{build_history(view)}\n\n"
        f"## Situação atual\nRodada {view.round}. Jogadores vivos: {', '.join(view.alive)}.\n\n"
        f"## Sua vez\n{task}"
    )


# --------------------------------------------------------------------------- #
# Ferramentas: uma por tipo de decisão
# --------------------------------------------------------------------------- #
# O enum com os nomes válidos é gerado na hora. Com `strict`, o modelo não
# consegue inventar um nome que não existe.


def _thought_field() -> dict:
    return {
        "type": "string",
        "description": "Seu raciocínio privado, curto (1 a 2 frases). Ninguém mais vê isto.",
    }


def _schema(properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def night_request(view: PlayerView) -> tuple[str, ToolSpec] | None:
    """Monta o pedido da ação noturna, ou None se o papel não age à noite."""
    if view.role is Role.WEREWOLF:
        options = [p for p in view.others_alive if p not in view.allies]
        task = "É noite. Escolha quem os lobisomens devem atacar."
        what = "o jogador a ser atacado"
    elif view.role is Role.SEER:
        options = view.others_alive
        task = "É noite. Escolha um jogador para investigar. Evite repetir quem você já investigou."
        what = "o jogador a ser investigado"
    elif view.role is Role.DOCTOR:
        options = view.alive
        task = "É noite. Escolha um jogador para proteger do ataque dos lobos (pode ser você)."
        what = "o jogador a ser protegido"
    else:
        return None
    if not options:
        return None
    tool = ToolSpec(
        name="acao_noturna",
        description="Registra sua ação secreta desta noite.",
        parameters=_schema({
            "pensamento": _thought_field(),
            "alvo": {"type": "string", "enum": options, "description": f"Nome de {what}."},
        }),
    )
    return _situation(view, task + " Use a ferramenta acao_noturna."), tool


def _speak_task(view: PlayerView) -> str:
    """
    Instruções da fala. Modelos pequenos tendem a copiar o que acabaram de ler,
    então listamos o que já foi dito nesta rodada e pedimos algo diferente.
    """
    said_now = [
        f'- {e.actor}: "{e.content}"'
        for e in view.events
        if e.kind is EventKind.SPEECH and e.round == view.round and e.actor != view.me
    ]
    mine_before = [f'- "{e.content}"' for e in view.events if e.kind is EventKind.SPEECH and e.actor == view.me]

    parts = ["É dia. Chegou sua vez de falar na discussão."]
    if said_now:
        parts.append("Já falaram nesta rodada:\n" + "\n".join(said_now))
    if mine_before:
        parts.append("Suas falas anteriores:\n" + "\n".join(mine_before))
    parts.append(
        "Regras para a sua fala:\n"
        "- NÃO repita nem parafraseie o que já foi dito (nem por você). Traga um ponto novo.\n"
        "- Seja específico: cite pelo menos um jogador pelo nome e o motivo (um voto, uma fala, uma morte, uma contradição).\n"
        "- Na maioria das vezes, acuse alguém ou defenda alguém acusado. Só use 'ninguem' se tiver um bom motivo.\n"
        "- Combine com a sua personalidade."
    )
    if view.round == 1 and not said_now:
        parts.append("Você é o primeiro a falar e ainda há pouca informação: comente a noite e lance uma suspeita ou pergunta a alguém.")
    parts.append("Use a ferramenta falar.")
    return "\n\n".join(parts)


def speak_request(view: PlayerView) -> tuple[str, ToolSpec]:
    options = view.others_alive + [NOBODY]
    tool = ToolSpec(
        name="falar",
        description="Diz algo para todos os jogadores na discussão do dia.",
        parameters=_schema({
            "pensamento": _thought_field(),
            "fala": {"type": "string", "description": "O que você diz em voz alta (1 a 3 frases)."},
            "acusado": {
                "type": "string",
                "enum": options,
                "description": f"Quem você está acusando nesta fala, ou '{NOBODY}'.",
            },
        }),
    )
    return _situation(view, _speak_task(view)), tool


def vote_request(view: PlayerView) -> tuple[str, ToolSpec]:
    options = view.others_alive + [NOBODY]
    tool = ToolSpec(
        name="votar",
        description="Registra seu voto para eliminar um jogador.",
        parameters=_schema({
            "pensamento": _thought_field(),
            "alvo": {
                "type": "string",
                "enum": options,
                "description": f"Em quem você vota para eliminar, ou '{NOBODY}' para se abster.",
            },
        }),
    )
    task = "É hora da votação. Os votos são abertos. Use a ferramenta votar."
    return _situation(view, task), tool
