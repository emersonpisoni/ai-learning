from django.test import TestCase
from django.urls import reverse

from game.models import GameEvent, Match
from game.services import create_match, run_match


class ServiceTests(TestCase):
    def test_create_and_run_match_persists_everything(self):
        match = run_match(create_match(num_players=8, seed=123))

        self.assertEqual(match.status, Match.Status.FINISHED)
        self.assertEqual(match.players.count(), 8)
        self.assertGreater(match.events.count(), 10)
        self.assertEqual(match.events.last().kind, "fim_de_jogo")
        # A ordem dos eventos é contínua (0, 1, 2, ...)
        orders = list(match.events.values_list("order", flat=True))
        self.assertEqual(orders, list(range(len(orders))))

    def test_same_seed_produces_same_events(self):
        a = run_match(create_match(seed=99))
        b = run_match(create_match(seed=99))
        content = lambda m: list(m.events.values_list("content", flat=True))  # noqa: E731
        self.assertEqual(content(a), content(b))


class ViewTests(TestCase):
    def test_index_and_new_match_flow(self):
        self.assertEqual(self.client.get(reverse("game:index")).status_code, 200)

        response = self.client.post(reverse("game:new"), {"num_players": 6, "seed": 5})
        match = Match.objects.get()
        self.assertRedirects(response, match.get_absolute_url())

        page = self.client.get(match.get_absolute_url())
        self.assertContains(page, "Rodada 1")
        self.assertContains(page, "god-mode")

    def test_invalid_player_count_shows_error(self):
        response = self.client.post(reverse("game:new"), {"num_players": 3}, follow=True)
        self.assertContains(response, "pelo menos 5")
        self.assertFalse(GameEvent.objects.exists())
