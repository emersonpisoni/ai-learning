"""
Camada de serviço: a ponte entre o motor (engine.py) e o banco (models.py).

Views, comandos de terminal e (no futuro) tarefas do Celery chamam estas
funções. Nenhum deles precisa saber como o motor funciona por dentro.
"""

from __future__ import annotations

import random
from collections import Counter
from itertools import count

from django.db import transaction

from .agents import AGENT_REGISTRY
from .engine import Event, Game, PlayerState, Role, Team, assign_roles
from .models import GameEvent, Match, Player

DEFAULT_NAMES = [
    "Ana", "Bruno", "Carla", "Diego", "Elisa", "Felipe",
    "Gabi", "Heitor", "Isis", "João", "Lara", "Mateus",
]


def _pick_names(num_players: int, names: list[str] | None) -> list[str]:
    names = names or DEFAULT_NAMES
    if num_players > len(names):
        raise ValueError(f"Máximo de {len(names)} jogadores com a lista de nomes atual.")
    return names[:num_players]


@transaction.atomic
def create_match(num_players: int = 8, seed: int | None = None, names: list[str] | None = None) -> Match:
    seed = seed if seed is not None else random.randrange(1_000_000)
    names = _pick_names(num_players, names)
    roles = assign_roles(len(names), random.Random(seed))

    match = Match.objects.create(seed=seed)
    Player.objects.bulk_create(
        Player(match=match, seat=i, name=name, role=role) for i, (name, role) in enumerate(zip(names, roles))
    )
    return match


def build_agents(players: list[Player], seed: int) -> dict:
    return {p.name: AGENT_REGISTRY[p.agent_type](seed=f"{seed}-{p.name}") for p in players}


def run_match(match: Match) -> Match:
    """Joga a partida inteira e salva cada evento no banco."""
    db_players = list(match.players.all())
    states = [PlayerState(name=p.name, role=Role(p.role), personality=p.personality) for p in db_players]
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

    game = Game(states, build_agents(db_players, match.seed), seed=match.seed, on_event=save_event)

    match.status = Match.Status.RUNNING
    match.save(update_fields=["status"])

    with transaction.atomic():
        winner = game.run()
        alive = set(game.alive_names)
        for p in db_players:
            p.alive = p.name in alive
        Player.objects.bulk_update(db_players, ["alive"])

        match.status = Match.Status.FINISHED
        match.winner = winner.value if winner else ""
        match.rounds_played = game.round
        match.save(update_fields=["status", "winner", "rounds_played"])
    return match


def simulate(num_players: int, seed: int) -> Team | None:
    """Roda uma partida só em memória (sem banco). Rápido para estatísticas."""
    names = _pick_names(num_players, None)
    roles = assign_roles(num_players, random.Random(seed))
    states = [PlayerState(n, r) for n, r in zip(names, roles)]
    agents = {n: AGENT_REGISTRY["random"](seed=f"{seed}-{n}") for n in names}
    return Game(states, agents, seed=seed).run()


def win_rates(num_players: int, games: int, first_seed: int = 0) -> Counter:
    return Counter(simulate(num_players, first_seed + i) for i in range(games))
