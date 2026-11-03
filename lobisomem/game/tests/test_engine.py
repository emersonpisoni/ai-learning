"""
Testes do motor. Repare que não usam banco nem Django: o motor é Python puro,
por isso usamos unittest.TestCase (bem mais rápido).
"""

import random
import unittest

from game.agents import RandomAgent
from game.engine import (
    Action,
    EventKind,
    Game,
    Phase,
    PlayerState,
    PlayerView,
    Role,
    Team,
    assign_roles,
)


class ScriptedAgent:
    """Agente "roteirizado" para testes: sempre escolhe os mesmos alvos."""

    def __init__(self, night=None, vote=None, accuse=None):
        self._night, self._vote, self._accuse = night, vote, accuse

    def night_action(self, view: PlayerView) -> Action:
        return Action(target=self._night, thought="roteiro")

    def speak(self, view: PlayerView) -> Action:
        return Action(target=self._accuse, text="oi")

    def vote(self, view: PlayerView) -> Action:
        return Action(target=self._vote)


def make_game(spec, **kwargs):
    """spec: lista de (nome, papel, ScriptedAgent)."""
    players = [PlayerState(name, role) for name, role, _ in spec]
    agents = {name: agent for name, _, agent in spec}
    return Game(players, agents, seed=1, **kwargs)


class AssignRolesTests(unittest.TestCase):
    def test_role_counts(self):
        roles = assign_roles(8, random.Random(0))
        self.assertEqual(roles.count(Role.WEREWOLF), 2)
        self.assertEqual(roles.count(Role.SEER), 1)
        self.assertEqual(roles.count(Role.DOCTOR), 1)
        self.assertEqual(roles.count(Role.VILLAGER), 4)

    def test_minimum_players(self):
        with self.assertRaises(ValueError):
            assign_roles(4, random.Random(0))


class GameRulesTests(unittest.TestCase):
    def test_doctor_saves_the_victim(self):
        game = make_game([
            ("Lobo", Role.WEREWOLF, ScriptedAgent(night="Ana")),
            ("Doc", Role.DOCTOR, ScriptedAgent(night="Ana")),
            ("Ana", Role.VILLAGER, ScriptedAgent()),
            ("Bia", Role.VILLAGER, ScriptedAgent()),
            ("Vi", Role.SEER, ScriptedAgent(night="Lobo")),
        ])
        game.step()  # noite
        self.assertTrue(game.players["Ana"].alive)
        self.assertIn(EventKind.SAVE, [e.kind for e in game.events])

    def test_wolf_kills_unprotected_victim(self):
        game = make_game([
            ("Lobo", Role.WEREWOLF, ScriptedAgent(night="Ana")),
            ("Doc", Role.DOCTOR, ScriptedAgent(night="Bia")),
            ("Ana", Role.VILLAGER, ScriptedAgent()),
            ("Bia", Role.VILLAGER, ScriptedAgent()),
            ("Vi", Role.SEER, ScriptedAgent(night="Lobo")),
        ])
        game.step()
        self.assertFalse(game.players["Ana"].alive)
        self.assertIs(game.phase, Phase.DISCUSSION)

    def test_village_wins_by_voting_out_the_wolf(self):
        game = make_game([
            ("Lobo", Role.WEREWOLF, ScriptedAgent(night="Ana", vote="Bia")),
            ("Doc", Role.DOCTOR, ScriptedAgent(night="Ana", vote="Lobo")),
            ("Ana", Role.VILLAGER, ScriptedAgent(vote="Lobo")),
            ("Bia", Role.VILLAGER, ScriptedAgent(vote="Lobo")),
            ("Vi", Role.SEER, ScriptedAgent(night="Lobo", vote="Lobo")),
        ])
        self.assertIs(game.run(), Team.VILLAGE)
        self.assertEqual(game.events[-1].kind, EventKind.GAME_OVER)

    def test_tie_vote_eliminates_nobody(self):
        game = make_game([
            ("Lobo", Role.WEREWOLF, ScriptedAgent(vote="Ana")),
            ("Doc", Role.DOCTOR, ScriptedAgent(vote="Lobo")),
            ("Ana", Role.VILLAGER, ScriptedAgent(vote="Lobo")),
            ("Bia", Role.VILLAGER, ScriptedAgent(vote="Ana")),
            ("Vi", Role.SEER, ScriptedAgent()),  # abstém
        ])
        game.phase = Phase.VOTE
        game.step()
        self.assertEqual(len(game.alive), 5)
        self.assertIn(EventKind.NO_ELIMINATION, [e.kind for e in game.events])

    def test_invalid_targets_are_ignored(self):
        """Agentes (principalmente LLMs) às vezes inventam nomes. O jogo não pode quebrar."""
        game = make_game([
            ("Lobo", Role.WEREWOLF, ScriptedAgent(night="Fantasma", vote="Lobo")),
            ("Doc", Role.DOCTOR, ScriptedAgent(night="Ninguém")),
            ("Ana", Role.VILLAGER, ScriptedAgent()),
            ("Bia", Role.VILLAGER, ScriptedAgent()),
            ("Vi", Role.SEER, ScriptedAgent(night="Vi")),  # não pode investigar a si mesma
        ])
        game.step()
        self.assertEqual(len(game.alive), 5)
        self.assertNotIn(EventKind.INVESTIGATION, [e.kind for e in game.events])


class VisibilityTests(unittest.TestCase):
    def test_private_events_only_reach_their_owner(self):
        game = make_game([
            ("Lobo", Role.WEREWOLF, ScriptedAgent(night="Ana")),
            ("Lobo2", Role.WEREWOLF, ScriptedAgent(night="Ana")),
            ("Doc", Role.DOCTOR, ScriptedAgent(night="Doc")),
            ("Ana", Role.VILLAGER, ScriptedAgent()),
            ("Bia", Role.VILLAGER, ScriptedAgent()),
            ("Caio", Role.VILLAGER, ScriptedAgent()),
            ("Duda", Role.VILLAGER, ScriptedAgent()),
            ("Vi", Role.SEER, ScriptedAgent(night="Lobo")),
        ])
        game.step()

        def kinds(name):
            return {e.kind for e in game.view_for(name).events}

        self.assertIn(EventKind.WOLF_VOTE, kinds("Lobo2"))
        self.assertNotIn(EventKind.WOLF_VOTE, kinds("Bia"))
        self.assertIn(EventKind.INVESTIGATION, kinds("Vi"))
        self.assertNotIn(EventKind.INVESTIGATION, kinds("Lobo"))
        self.assertEqual(game.view_for("Lobo").allies, ["Lobo2"])
        self.assertEqual(game.view_for("Bia").allies, [])


class RandomGamesTests(unittest.TestCase):
    def test_many_random_games_always_finish(self):
        names = [f"J{i}" for i in range(8)]
        for seed in range(200):
            roles = assign_roles(8, random.Random(seed))
            players = [PlayerState(n, r) for n, r in zip(names, roles)]
            agents = {n: RandomAgent(seed=f"{seed}-{n}") for n in names}
            game = Game(players, agents, seed=seed)
            game.run()
            self.assertIs(game.phase, Phase.FINISHED)

    def test_same_seed_same_game(self):
        def play(seed):
            names = [f"J{i}" for i in range(7)]
            roles = assign_roles(7, random.Random(seed))
            players = [PlayerState(n, r) for n, r in zip(names, roles)]
            game = Game(players, {n: RandomAgent(seed=f"{seed}-{n}") for n in names}, seed=seed)
            game.run()
            return [e.content for e in game.events]

        self.assertEqual(play(7), play(7))
