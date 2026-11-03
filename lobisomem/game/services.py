"""
Camada de serviço: a ponte entre o motor (engine.py) e o banco (models.py).

Views, comandos de terminal e (no futuro) tarefas do Celery chamam estas
funções. Nenhum deles precisa saber como o motor funciona por dentro.
"""

from __future__ import annotations

import logging
import random
import threading
from collections import Counter
from itertools import count

from django.db import connection, transaction

from .agents import AGENT_REGISTRY, LLMAgent
from .engine import Event, EventKind, Game, PlayerState, Role, Team, assign_roles
from .llm import get_client
from .models import GameEvent, Match, Player
from .prompts import PERSONALITIES

logger = logging.getLogger(__name__)

DEFAULT_NAMES = [
    "Ana", "Bruno", "Carla", "Diego", "Elisa", "Felipe",
    "Gabi", "Heitor", "Isis", "João", "Lara", "Mateus",
]


def _pick_names(num_players: int, names: list[str] | None) -> list[str]:
    names = names or DEFAULT_NAMES
    if num_players > len(names):
        raise ValueError(f"Máximo de {len(names)} jogadores com a lista de nomes atual.")
    return names[:num_players]


AGENT_MODES = {
    "random": "Aleatórios (sem IA)",
    "llm": "Todos com IA",
    "misto": "Metade IA, metade aleatórios",
}


def _agent_types(mode: str, roles: list[Role], rng: random.Random) -> list[str]:
    if mode == "random":
        return ["random"] * len(roles)
    if mode == "llm":
        return ["llm"] * len(roles)
    if mode == "misto":
        # Metade com IA, garantindo IA nos dois times para a comparação ser justa.
        types = ["llm" if i % 2 == 0 else "random" for i in range(len(roles))]
        rng.shuffle(types)
        wolves = [i for i, r in enumerate(roles) if r is Role.WEREWOLF]
        if wolves and all(types[i] == "random" for i in wolves):
            types[wolves[0]] = "llm"
        return types
    raise ValueError(f"Modo de agentes inválido: {mode!r}")


@transaction.atomic
def create_match(
    num_players: int = 8,
    seed: int | None = None,
    names: list[str] | None = None,
    agent_mode: str = "random",
) -> Match:
    seed = seed if seed is not None else random.randrange(1_000_000)
    names = _pick_names(num_players, names)
    rng = random.Random(seed)
    roles = assign_roles(len(names), rng)
    agent_types = _agent_types(agent_mode, roles, rng)
    personalities = rng.sample(PERSONALITIES, len(names))

    match = Match.objects.create(seed=seed)
    Player.objects.bulk_create(
        Player(
            match=match,
            seat=i,
            name=name,
            role=role,
            agent_type=agent_type,
            personality=personality if agent_type == "llm" else "",
        )
        for i, (name, role, agent_type, personality) in enumerate(zip(names, roles, agent_types, personalities))
    )
    return match


def build_agents(players: list[Player], seed: int, client=None) -> dict:
    """Cria um agente para cada jogador. Os agentes com IA compartilham o mesmo cliente."""
    agents = {}
    for p in players:
        agent_seed = f"{seed}-{p.name}"
        if p.agent_type == "llm":
            client = client or get_client()
            agents[p.name] = LLMAgent(seed=agent_seed, personality=p.personality, client=client)
        else:
            agents[p.name] = AGENT_REGISTRY[p.agent_type](seed=agent_seed)
    return agents


def run_match(match: Match, client=None, on_event=None) -> Match:
    """
    Joga a partida inteira e salva cada evento no banco assim que acontece.

    Os eventos são gravados um a um (sem uma transação em volta do jogo
    inteiro) para que a tela consiga mostrar a partida enquanto ela roda.
    """
    db_players = {p.name: p for p in match.players.all()}
    states = [PlayerState(name=p.name, role=Role(p.role), personality=p.personality) for p in db_players.values()]
    order = count(start=match.events.count())

    def save_event(event: Event) -> None:
        # Este callback é o gancho para o tempo real: na etapa 4, além de
        # salvar, ele vai mandar o evento pelo WebSocket (Django Channels).
        GameEvent.objects.create(
            match=match,
            order=next(order),
            round=event.round,
            phase=event.phase,
            kind=event.kind,
            actor=event.actor or "",
            target=event.target or "",
            content=event.content,
            visibility=event.visibility,
            thought=event.thought,
        )
        if event.kind in (EventKind.KILL, EventKind.ELIMINATION) and event.target:
            Player.objects.filter(match=match, name=event.target).update(alive=False)
        if event.round != match.rounds_played:
            match.rounds_played = event.round
            match.save(update_fields=["rounds_played"])
        if on_event:  # gancho extra (o comando de terminal usa para imprimir ao vivo)
            on_event(event)

    match.status = Match.Status.RUNNING
    match.save(update_fields=["status"])

    try:
        game = Game(states, build_agents(list(db_players.values()), match.seed, client), seed=match.seed, on_event=save_event)
        winner = game.run()
    except Exception as exc:  # erro de configuração (ex.: chave da API inválida)
        logger.exception("Partida %s falhou", match.pk)
        match.status = Match.Status.ERROR
        match.error = f"{type(exc).__name__}: {exc}"
        match.save(update_fields=["status", "error"])
        return match

    match.status = Match.Status.FINISHED
    match.winner = winner.value if winner else ""
    match.rounds_played = game.round
    match.save(update_fields=["status", "winner", "rounds_played"])
    return match


def run_match_in_background(match_id: int) -> threading.Thread:
    """
    Roda a partida numa thread separada, para a página não ficar travada.

    É uma solução simples para estudo. Em produção, o certo é usar uma fila de
    tarefas como o Celery (é a etapa 4 do roteiro).
    """

    def target():
        try:
            run_match(Match.objects.get(pk=match_id))
        finally:
            connection.close()  # cada thread abre a própria conexão com o banco

    thread = threading.Thread(target=target, daemon=True, name=f"partida-{match_id}")
    thread.start()
    return thread


def simulate(num_players: int, seed: int) -> Team | None:
    """Roda uma partida só em memória (sem banco). Rápido para estatísticas."""
    names = _pick_names(num_players, None)
    roles = assign_roles(num_players, random.Random(seed))
    states = [PlayerState(n, r) for n, r in zip(names, roles)]
    agents = {n: AGENT_REGISTRY["random"](seed=f"{seed}-{n}") for n in names}
    return Game(states, agents, seed=seed).run()


def win_rates(num_players: int, games: int, first_seed: int = 0) -> Counter:
    return Counter(simulate(num_players, first_seed + i) for i in range(games))
