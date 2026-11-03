"""
Agentes que jogam Lobisomem.

Hoje só existe o RandomAgent: decide (quase) tudo no sorteio, mas com um
pouquinho de lógica para as partidas não serem totalmente sem sentido.
Ele serve de "linha de base": quando o agente com LLM chegar, ele precisa
ganhar mais do que este aqui.
"""

from __future__ import annotations

import random
from collections import Counter

from .engine import Action, EventKind, PlayerView, Role
from .llm import get_client
from .prompts import NOBODY, build_system, night_request, speak_request, vote_request

SUSPICIONS = [
    "Achei {t} quieto demais ontem. Estou de olho.",
    "Sei não… {t} mudou de assunto rápido demais.",
    "Meu voto hoje vai para {t}, algo não bate.",
    "Quem viu {t} acordado de madrugada? Muito estranho.",
]
NEUTRAL = [
    "Ainda não tenho certeza de nada. Vamos com calma.",
    "Precisamos pensar bem antes de votar.",
    "Eu sou inocente, só para deixar claro.",
    "Alguém tem alguma pista concreta?",
]


class RandomAgent:
    def __init__(self, seed: int | str | None = None) -> None:
        self.rng = random.Random(seed)

    # ----- helpers --------------------------------------------------------- #

    @staticmethod
    def _known_wolves(view: PlayerView) -> list[str]:
        """Para a vidente: quem ela já descobriu que é lobo e ainda está vivo."""
        return [
            e.target
            for e in view.events
            if e.kind is EventKind.INVESTIGATION and e.actor == view.me and "É lobisomem" in e.content
            and e.target in view.alive
        ]

    @staticmethod
    def _investigated(view: PlayerView) -> set[str]:
        return {e.target for e in view.events if e.kind is EventKind.INVESTIGATION and e.actor == view.me}

    @staticmethod
    def _todays_accusations(view: PlayerView) -> Counter[str]:
        return Counter(
            e.target
            for e in view.events
            if e.kind is EventKind.SPEECH and e.round == view.round and e.target in view.alive
        )

    # ----- Agent protocol -------------------------------------------------- #

    def night_action(self, view: PlayerView) -> Action:
        if view.role is Role.WEREWOLF:
            prey = [p for p in view.others_alive if p not in view.allies]
            target = self.rng.choice(prey) if prey else None
            return Action(target=target, thought=f"Hoje à noite vou atrás de {target}. Sorteio puro.")

        if view.role is Role.SEER:
            fresh = [p for p in view.others_alive if p not in self._investigated(view)]
            target = self.rng.choice(fresh or view.others_alive)
            return Action(target=target, thought=f"Vou investigar {target}.")

        if view.role is Role.DOCTOR:
            target = self.rng.choice(view.alive)
            return Action(target=target, thought=f"Meu palpite é que vão atacar {target}.")

        return Action(thought="Sou aldeão, só durmo.")

    def speak(self, view: PlayerView) -> Action:
        known = self._known_wolves(view)
        if view.role is Role.SEER and known:
            t = known[0]
            return Action(
                target=t,
                text=f"Tenho certeza: {t} é lobisomem. Confiem em mim!",
                thought=f"Investiguei {t} e confirmei. Hora de me arriscar.",
            )

        if self.rng.random() < 0.5:
            pool = [p for p in view.others_alive if p not in view.allies]
            t = self.rng.choice(pool) if pool else None
            if t:
                thought = (
                    f"Vou jogar a culpa em {t} para desviar a atenção."
                    if view.role is Role.WEREWOLF
                    else f"Não tenho prova nenhuma contra {t}, mas alguém tem que puxar o assunto."
                )
                return Action(target=t, text=self.rng.choice(SUSPICIONS).format(t=t), thought=thought)

        thought = "Melhor ficar discreto." if view.role is Role.WEREWOLF else "Ainda sem pistas."
        return Action(text=self.rng.choice(NEUTRAL), thought=thought)

    def vote(self, view: PlayerView) -> Action:
        known = self._known_wolves(view)
        if known:
            return Action(target=known[0], thought="Voto em quem eu sei que é lobo.")

        if view.role is Role.WEREWOLF:
            pool = [p for p in view.others_alive if p not in view.allies]
            t = self.rng.choice(pool) if pool else None
            return Action(target=t, thought="Qualquer um que não seja da matilha.")

        # Aldeões tendem a seguir a acusação mais popular do dia.
        accusations = self._todays_accusations(view)
        accusations.pop(view.me, None)
        if accusations and self.rng.random() < 0.6:
            t = accusations.most_common(1)[0][0]
            return Action(target=t, thought=f"Muita gente desconfiou de {t}. Vou na onda.")

        t = self.rng.choice(view.others_alive) if view.others_alive else None
        return Action(target=t, thought="Chute no escuro.")


class LLMAgent:
    """
    Agente que decide usando um LLM.

    Ele não guarda estado entre as chamadas: a cada decisão, monta o prompt do
    zero a partir da PlayerView (o histórico que o jogador viu). Isso deixa o
    agente simples e garante que ele nunca "lembre" de algo que não poderia saber.

    Se a IA falhar (erro de rede, resposta sem ferramenta, recusa), o agente
    faz uma jogada aleatória e avisa no pensamento. O jogo nunca para por isso.
    """

    def __init__(self, seed=None, personality: str = "", client=None) -> None:
        self.personality = personality
        self.client = client or get_client()
        self.fallback = RandomAgent(seed=seed)

    def _ask(self, view: PlayerView, request) -> dict | None:
        prompt, tool = request
        return self.client.call_tool(build_system(view, self.personality), prompt, tool)

    @staticmethod
    def _target(value) -> str | None:
        return None if value in (None, "", NOBODY) else value

    def _failed(self, action: Action) -> Action:
        action.thought = f"⚠️ A IA não respondeu; jogada aleatória. ({action.thought})"
        return action

    # ----- Agent protocol -------------------------------------------------- #

    def night_action(self, view: PlayerView) -> Action:
        request = night_request(view)
        if request is None:  # aldeão não age à noite: nem chama a IA
            return Action(thought="Sou aldeão, só durmo.")
        args = self._ask(view, request)
        if not args:
            return self._failed(self.fallback.night_action(view))
        return Action(target=self._target(args.get("alvo")), thought=args.get("pensamento", ""))

    def speak(self, view: PlayerView) -> Action:
        args = self._ask(view, speak_request(view))
        if not args or not args.get("fala"):
            return self._failed(self.fallback.speak(view))
        return Action(
            target=self._target(args.get("acusado")),
            text=args["fala"].strip(),
            thought=args.get("pensamento", ""),
        )

    def vote(self, view: PlayerView) -> Action:
        args = self._ask(view, vote_request(view))
        if not args:
            return self._failed(self.fallback.vote(view))
        return Action(target=self._target(args.get("alvo")), thought=args.get("pensamento", ""))


# Registro de tipos de agente: o nome guardado em Player.agent_type → a classe.
AGENT_REGISTRY: dict[str, type] = {
    "random": RandomAgent,
    "llm": LLMAgent,
}
