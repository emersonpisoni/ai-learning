"""
Motor do jogo Lobisomem — Python puro, sem Django e sem IA.

A ideia é que este arquivo seja a "fonte da verdade" das regras. O Django só
guarda o que acontece aqui, e os agentes (aleatórios hoje, LLMs amanhã) só
tomam decisões. Assim cada parte pode ser testada isoladamente.

Fluxo de uma rodada (máquina de estados):

    NOITE ──► DISCUSSÃO ──► VOTAÇÃO ──► NOITE (próxima rodada) ...
                                   └──► FIM (quando alguém vence)
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable, Protocol


# --------------------------------------------------------------------------- #
# Tipos básicos
# --------------------------------------------------------------------------- #


class Team(StrEnum):
    VILLAGE = "aldeia"
    WOLVES = "lobisomens"


class Role(StrEnum):
    WEREWOLF = "lobisomem"
    VILLAGER = "aldeao"
    SEER = "vidente"
    DOCTOR = "medico"

    @property
    def team(self) -> Team:
        return Team.WOLVES if self is Role.WEREWOLF else Team.VILLAGE

    @property
    def label(self) -> str:
        return {
            Role.WEREWOLF: "Lobisomem",
            Role.VILLAGER: "Aldeão",
            Role.SEER: "Vidente",
            Role.DOCTOR: "Médico",
        }[self]


class Phase(StrEnum):
    NIGHT = "noite"
    DISCUSSION = "discussao"
    VOTE = "votacao"
    FINISHED = "fim"


class EventKind(StrEnum):
    PHASE = "fase"
    WOLF_VOTE = "voto_lobo"
    INVESTIGATION = "investigacao"
    PROTECTION = "protecao"
    KILL = "morte"
    SAVE = "salvamento"
    SPEECH = "fala"
    VOTE = "voto"
    ELIMINATION = "eliminacao"
    NO_ELIMINATION = "sem_eliminacao"
    GAME_OVER = "fim_de_jogo"


# Visibilidade de um evento: todos, só os lobos, ou o nome de um jogador.
PUBLIC = "public"
WOLVES_ONLY = "wolves"


@dataclass
class PlayerState:
    name: str
    role: Role
    alive: bool = True
    personality: str = ""


@dataclass
class Event:
    """Tudo o que acontece no jogo vira um Event. É o "log" da partida."""

    round: int
    phase: Phase
    kind: EventKind
    content: str
    actor: str | None = None
    target: str | None = None
    visibility: str = PUBLIC
    # O que o agente "pensou" ao tomar a decisão. Nunca é mostrado a outros
    # jogadores — só aparece no "modo deus" da interface.
    thought: str = ""

    def is_visible_to(self, player: PlayerState) -> bool:
        if self.visibility == PUBLIC:
            return True
        if self.visibility == WOLVES_ONLY:
            return player.role is Role.WEREWOLF
        return self.visibility == player.name


@dataclass(frozen=True)
class PlayerView:
    """
    O que UM jogador consegue ver do jogo. É isso (e só isso) que o agente
    recebe — ele nunca enxerga o estado completo. Quando trocarmos por um LLM,
    é esta view que vira o prompt.
    """

    me: str
    role: Role
    round: int
    phase: Phase
    alive: list[str]
    allies: list[str]  # outros lobos (vazio para quem não é lobo)
    events: list[Event]

    @property
    def others_alive(self) -> list[str]:
        return [p for p in self.alive if p != self.me]


@dataclass
class Action:
    """A resposta de um agente. `target` é um nome de jogador (ou None)."""

    target: str | None = None
    text: str = ""
    thought: str = ""


class Agent(Protocol):
    """
    Contrato que qualquer agente precisa cumprir. O RandomAgent implementa
    hoje; um LLMAgent vai implementar na próxima etapa — o motor nem percebe
    a diferença.
    """

    def night_action(self, view: PlayerView) -> Action:
        """Lobo: quem atacar. Vidente: quem investigar. Médico: quem proteger."""
        ...

    def speak(self, view: PlayerView) -> Action:
        """Fala durante a discussão. `target` = quem está sendo acusado (opcional)."""
        ...

    def vote(self, view: PlayerView) -> Action:
        """Em quem votar para eliminar. `target=None` = abstenção."""
        ...


# --------------------------------------------------------------------------- #
# Distribuição de papéis
# --------------------------------------------------------------------------- #


def assign_roles(num_players: int, rng: random.Random) -> list[Role]:
    """1 lobo a cada 4 jogadores, 1 vidente, 1 médico e o resto aldeões."""
    if num_players < 5:
        raise ValueError("São necessários pelo menos 5 jogadores.")
    wolves = max(1, num_players // 4)
    roles = [Role.WEREWOLF] * wolves + [Role.SEER, Role.DOCTOR]
    roles += [Role.VILLAGER] * (num_players - len(roles))
    rng.shuffle(roles)
    return roles


# --------------------------------------------------------------------------- #
# O jogo
# --------------------------------------------------------------------------- #


class Game:
    def __init__(
        self,
        players: list[PlayerState],
        agents: dict[str, Agent],
        *,
        seed: int | str | None = None,
        on_event: Callable[[Event], None] | None = None,
        max_rounds: int = 20,
    ) -> None:
        names = [p.name for p in players]
        if len(set(names)) != len(names):
            raise ValueError("Nomes de jogadores precisam ser únicos.")
        if set(agents) != set(names):
            raise ValueError("Cada jogador precisa de exatamente um agente.")

        self.players = {p.name: p for p in players}
        self.agents = agents
        self.rng = random.Random(seed)
        self.on_event = on_event
        self.max_rounds = max_rounds

        self.round = 1
        self.phase = Phase.NIGHT
        self.winner: Team | None = None
        self.events: list[Event] = []

    # ----- consultas ------------------------------------------------------- #

    @property
    def alive(self) -> list[PlayerState]:
        return [p for p in self.players.values() if p.alive]

    @property
    def alive_names(self) -> list[str]:
        return [p.name for p in self.alive]

    def alive_with(self, role: Role) -> list[PlayerState]:
        return [p for p in self.alive if p.role is role]

    def view_for(self, name: str) -> PlayerView:
        me = self.players[name]
        allies = (
            [p.name for p in self.players.values() if p.role is Role.WEREWOLF and p.name != name]
            if me.role is Role.WEREWOLF
            else []
        )
        return PlayerView(
            me=name,
            role=me.role,
            round=self.round,
            phase=self.phase,
            alive=self.alive_names,
            allies=allies,
            events=[e for e in self.events if e.is_visible_to(me)],
        )

    # ----- execução -------------------------------------------------------- #

    def run(self) -> Team | None:
        """Joga a partida inteira. Retorna o time vencedor (None = empate)."""
        while self.phase is not Phase.FINISHED:
            self.step()
        return self.winner

    def step(self) -> None:
        """Executa UMA fase. Útil para rodar a partida passo a passo (ex.: com Celery)."""
        handlers = {
            Phase.NIGHT: self._night,
            Phase.DISCUSSION: self._discussion,
            Phase.VOTE: self._vote,
        }
        if self.phase is Phase.FINISHED:
            return
        handlers[self.phase]()

    # ----- fases ----------------------------------------------------------- #

    def _night(self) -> None:
        self._announce_phase(f"🌙 Noite {self.round} — a aldeia dorme.")

        # 1) Lobos escolhem uma vítima (maioria dos votos dos lobos).
        wolf_votes: list[str] = []
        for wolf in self.alive_with(Role.WEREWOLF):
            options = [p.name for p in self.alive if p.role is not Role.WEREWOLF]
            action = self.agents[wolf.name].night_action(self.view_for(wolf.name))
            target = self._valid(action.target, options)
            if target:
                wolf_votes.append(target)
            self._emit(
                EventKind.WOLF_VOTE,
                f"{wolf.name} quer atacar {target}." if target else f"{wolf.name} não escolheu ninguém.",
                actor=wolf.name,
                target=target,
                visibility=WOLVES_ONLY,
                thought=action.thought,
            )
        victim = self._plurality(wolf_votes, break_ties=True)

        # 2) Vidente investiga alguém.
        for seer in self.alive_with(Role.SEER):
            action = self.agents[seer.name].night_action(self.view_for(seer.name))
            target = self._valid(action.target, [n for n in self.alive_names if n != seer.name])
            if target:
                is_wolf = self.players[target].role is Role.WEREWOLF
                self._emit(
                    EventKind.INVESTIGATION,
                    f"🔮 {target} {'É' if is_wolf else 'NÃO é'} lobisomem.",
                    actor=seer.name,
                    target=target,
                    visibility=seer.name,
                    thought=action.thought,
                )

        # 3) Médico protege alguém (pode ser ele mesmo).
        protected: str | None = None
        for doctor in self.alive_with(Role.DOCTOR):
            action = self.agents[doctor.name].night_action(self.view_for(doctor.name))
            protected = self._valid(action.target, self.alive_names)
            if protected:
                self._emit(
                    EventKind.PROTECTION,
                    f"🩺 Você protegeu {protected} esta noite.",
                    actor=doctor.name,
                    target=protected,
                    visibility=doctor.name,
                    thought=action.thought,
                )

        # 4) Resolve a noite.
        if victim and victim == protected:
            self._emit(EventKind.SAVE, "☀️ A aldeia acorda… e ninguém morreu esta noite!", target=victim)
        elif victim:
            self.players[victim].alive = False
            self._emit(
                EventKind.KILL,
                f"☀️ A aldeia acorda e encontra {victim} morto. Era {self.players[victim].role.label}.",
                target=victim,
            )
        else:
            self._emit(EventKind.SAVE, "☀️ A noite foi tranquila. Ninguém morreu.")

        self._advance(Phase.DISCUSSION)

    def _discussion(self) -> None:
        self._announce_phase(f"💬 Dia {self.round} — hora de discutir.")
        speakers = self.alive_names
        self.rng.shuffle(speakers)
        for name in speakers:
            action = self.agents[name].speak(self.view_for(name))
            accused = self._valid(action.target, [n for n in self.alive_names if n != name])
            self._emit(
                EventKind.SPEECH,
                action.text or "…",
                actor=name,
                target=accused,
                thought=action.thought,
            )
        self._advance(Phase.VOTE)

    def _vote(self) -> None:
        self._announce_phase(f"🗳️ Dia {self.round} — votação.")
        votes: list[str] = []
        for name in self.alive_names:
            action = self.agents[name].vote(self.view_for(name))
            target = self._valid(action.target, [n for n in self.alive_names if n != name])
            if target:
                votes.append(target)
            self._emit(
                EventKind.VOTE,
                f"{name} votou em {target}." if target else f"{name} se absteve.",
                actor=name,
                target=target,
                thought=action.thought,
            )

        eliminated = self._plurality(votes, break_ties=False)
        if eliminated:
            self.players[eliminated].alive = False
            tally = Counter(votes)[eliminated]
            self._emit(
                EventKind.ELIMINATION,
                f"⚖️ {eliminated} foi eliminado com {tally} voto(s). Era {self.players[eliminated].role.label}.",
                target=eliminated,
            )
        else:
            self._emit(EventKind.NO_ELIMINATION, "⚖️ Empate na votação. Ninguém foi eliminado.")

        self._advance(Phase.NIGHT)

    # ----- utilitários ----------------------------------------------------- #

    def _advance(self, next_phase: Phase) -> None:
        """Checa vitória antes de mudar de fase. Voltar para a noite = nova rodada."""
        winner = self._check_winner()
        if winner:
            self._finish(winner)
            return
        if next_phase is Phase.NIGHT:
            if self.round >= self.max_rounds:
                self._finish(None)
                return
            self.round += 1
        self.phase = next_phase

    def _check_winner(self) -> Team | None:
        wolves = len(self.alive_with(Role.WEREWOLF))
        others = len(self.alive) - wolves
        if wolves == 0:
            return Team.VILLAGE
        if wolves >= others:
            return Team.WOLVES
        return None

    def _finish(self, winner: Team | None) -> None:
        self.winner = winner
        self.phase = Phase.FINISHED
        msg = {
            Team.VILLAGE: "🎉 A aldeia venceu! Todos os lobisomens foram eliminados.",
            Team.WOLVES: "🐺 Os lobisomens venceram! Eles dominam a aldeia.",
            None: "⏳ Limite de rodadas atingido. Empate.",
        }[winner]
        self._emit(EventKind.GAME_OVER, msg)

    def _announce_phase(self, text: str) -> None:
        self._emit(EventKind.PHASE, text)

    def _emit(self, kind: EventKind, content: str, **kwargs) -> Event:
        event = Event(round=self.round, phase=self.phase, kind=kind, content=content, **kwargs)
        self.events.append(event)
        if self.on_event:
            self.on_event(event)
        return event

    @staticmethod
    def _valid(target: str | None, options: list[str]) -> str | None:
        """
        Agentes erram (principalmente LLMs!). Se o alvo não for válido,
        tratamos como "nenhuma ação" em vez de quebrar o jogo.
        """
        return target if target in options else None

    def _plurality(self, votes: list[str], *, break_ties: bool) -> str | None:
        if not votes:
            return None
        counts = Counter(votes).most_common()
        top = counts[0][1]
        leaders = [name for name, c in counts if c == top]
        if len(leaders) == 1:
            return leaders[0]
        return self.rng.choice(leaders) if break_ties else None
