"""
Testes da parte de IA. Nenhum chama uma IA de verdade: usamos o FakeClient,
que devolve respostas prontas e guarda os prompts para inspecionarmos.
"""

import io
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from game.agents import LLMAgent
from game.engine import Event, EventKind, Phase, PlayerView, Role
from game.llm import AnthropicClient, FakeClient, OllamaClient, ToolSpec
from game.models import Match
from game.prompts import NOBODY, build_history, build_system, night_request, speak_request, vote_request
from game.services import create_match, run_match


def first_option_responder(system, prompt, tool):
    """Responde sempre a primeira opção válida de cada campo com enum."""
    args = {"pensamento": f"pensando sobre {tool.name}"}
    for name, schema in tool.parameters["properties"].items():
        if "enum" in schema:
            args[name] = schema["enum"][0]
    if tool.name == "falar":
        args["fala"] = "Estou de olho em todo mundo."
    return args


def make_view(me="Ana", role=Role.VILLAGER, allies=(), events=()):
    return PlayerView(
        me=me, role=role, round=2, phase=Phase.DISCUSSION,
        alive=["Ana", "Bruno", "Carla", "Lobo"], allies=list(allies), events=list(events),
    )


class PromptTests(unittest.TestCase):
    def test_system_prompt_reveals_role_and_allies_only_to_wolves(self):
        wolf = build_system(make_view(me="Lobo", role=Role.WEREWOLF, allies=["Carla"]), "Teimosa")
        self.assertIn("Lobisomem", wolf)
        self.assertIn("Carla", wolf)
        self.assertIn("Teimosa", wolf)

        villager = build_system(make_view(), "")
        self.assertIn("Aldeão", villager)
        self.assertNotIn("aliados lobisomens são", villager)

    def test_history_shows_only_my_own_thoughts(self):
        events = [
            Event(1, Phase.DISCUSSION, EventKind.SPEECH, "Foi o Bruno!", actor="Ana", thought="chute meu"),
            Event(1, Phase.DISCUSSION, EventKind.SPEECH, "Não fui eu.", actor="Bruno", thought="sou lobo, disfarça"),
        ]
        history = build_history(make_view(events=events))
        self.assertIn("chute meu", history)
        self.assertNotIn("sou lobo", history)
        self.assertIn('Bruno: "Não fui eu."', history)

    def test_wolves_cannot_target_allies_at_night(self):
        _, tool = night_request(make_view(me="Lobo", role=Role.WEREWOLF, allies=["Carla"]))
        options = tool.parameters["properties"]["alvo"]["enum"]
        self.assertEqual(options, ["Ana", "Bruno"])

    def test_villagers_have_no_night_action(self):
        self.assertIsNone(night_request(make_view()))

    def test_vote_and_speech_allow_nobody_but_not_myself(self):
        for request in (vote_request(make_view()), speak_request(make_view())):
            _, tool = request
            field = "alvo" if tool.name == "votar" else "acusado"
            options = tool.parameters["properties"][field]["enum"]
            self.assertIn(NOBODY, options)
            self.assertNotIn("Ana", options)

    def test_schemas_are_strict_compatible(self):
        """O modo strict exige additionalProperties=false e todos os campos obrigatórios."""
        _, tool = speak_request(make_view())
        self.assertFalse(tool.parameters["additionalProperties"])
        self.assertEqual(set(tool.parameters["required"]), set(tool.parameters["properties"]))


class LLMAgentTests(unittest.TestCase):
    def test_maps_tool_arguments_to_actions(self):
        agent = LLMAgent(seed=1, client=FakeClient(first_option_responder))
        view = make_view()

        vote = agent.vote(view)
        self.assertEqual(vote.target, "Bruno")
        self.assertEqual(vote.thought, "pensando sobre votar")

        speech = agent.speak(view)
        self.assertEqual(speech.text, "Estou de olho em todo mundo.")

    def test_nobody_becomes_none(self):
        agent = LLMAgent(seed=1, client=FakeClient(lambda *a: {"pensamento": "", "alvo": NOBODY}))
        self.assertIsNone(agent.vote(make_view()).target)

    def test_falls_back_to_random_when_the_model_fails(self):
        agent = LLMAgent(seed=1, client=FakeClient(lambda *a: None))
        action = agent.vote(make_view())
        self.assertIn("⚠️", action.thought)
        self.assertIn(action.target, ["Bruno", "Carla", "Lobo"])

    def test_villager_night_does_not_call_the_model(self):
        client = FakeClient(first_option_responder)
        LLMAgent(seed=1, client=client).night_action(make_view())
        self.assertEqual(client.calls, [])


class AnthropicClientTests(unittest.TestCase):
    def _client(self, response):
        import anthropic

        client = AnthropicClient.__new__(AnthropicClient)  # pula o __init__ (não precisa de chave)
        client._anthropic = anthropic
        client.model, client.effort, client.max_tokens = "claude-opus-5-5", "low", 4000
        client.client = mock.Mock()
        client.client.beta.messages.create.return_value = response
        return client

    def test_sends_strict_tool_and_reads_tool_input(self):
        tool = ToolSpec("votar", "vota", {"type": "object", "properties": {}, "required": [], "additionalProperties": False})
        response = SimpleNamespace(
            stop_reason="tool_use",
            content=[SimpleNamespace(type="tool_use", name="votar", input={"alvo": "Ana"})],
        )
        client = self._client(response)

        self.assertEqual(client.call_tool("sys", "prompt", tool), {"alvo": "Ana"})
        kwargs = client.client.beta.messages.create.call_args.kwargs
        self.assertTrue(kwargs["tools"][0]["strict"])
        self.assertEqual(kwargs["fallbacks"], "default")
        self.assertEqual(kwargs["output_config"], {"effort": "low"})

    def test_refusal_returns_none(self):
        tool = ToolSpec("votar", "vota", {})
        client = self._client(SimpleNamespace(stop_reason="refusal", content=[]))
        with self.assertLogs("game.llm", level="WARNING"):
            self.assertIsNone(client.call_tool("sys", "prompt", tool))


class OllamaClientTests(unittest.TestCase):
    def test_parses_tool_calls(self):
        payload = {"message": {"tool_calls": [{"function": {"name": "votar", "arguments": {"alvo": "Bruno"}}}]}}
        fake_response = mock.MagicMock()
        fake_response.__enter__.return_value = io.BytesIO(json.dumps(payload).encode())
        with mock.patch("urllib.request.urlopen", return_value=fake_response):
            result = OllamaClient().call_tool("sys", "prompt", ToolSpec("votar", "vota", {}))
        self.assertEqual(result, {"alvo": "Bruno"})

    def test_connection_error_returns_none(self):
        import urllib.error

        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")), \
                self.assertLogs("game.llm", level="WARNING"):
            self.assertIsNone(OllamaClient().call_tool("sys", "prompt", ToolSpec("votar", "vota", {})))


class LLMMatchTests(TestCase):
    def test_full_llm_match_with_fake_client(self):
        match = create_match(num_players=6, seed=3, agent_mode="llm")
        self.assertTrue(all(p.agent_type == "llm" and p.personality for p in match.players.all()))

        match = run_match(match, client=FakeClient(first_option_responder))
        self.assertEqual(match.status, Match.Status.FINISHED)
        self.assertTrue(match.events.filter(kind="fala", content="Estou de olho em todo mundo.").exists())
        # Os mortos ficam marcados no banco durante a partida.
        self.assertTrue(match.players.filter(alive=False).exists())

    def test_mixed_mode_has_ai_on_both_teams(self):
        for seed in range(20):
            match = create_match(num_players=8, seed=seed, agent_mode="misto")
            players = list(match.players.all())
            self.assertEqual({p.agent_type for p in players}, {"llm", "random"})
            self.assertTrue(any(p.is_wolf and p.agent_type == "llm" for p in players))

    def test_configuration_error_marks_match_as_failed(self):
        def broken(*args):
            raise RuntimeError("chave inválida")

        with self.assertLogs("game.services", level="ERROR"):
            match = run_match(create_match(seed=1, agent_mode="llm"), client=FakeClient(broken))
        self.assertEqual(match.status, Match.Status.ERROR)
        self.assertIn("chave inválida", match.error)

    def test_live_endpoint_returns_html_and_status(self):
        match = run_match(create_match(seed=4))
        data = self.client.get(reverse("game:live", args=[match.pk])).json()
        self.assertEqual(data["status"], "finished")
        self.assertEqual(data["events"], match.events.count())
        self.assertIn("Rodada 1", data["html"])
