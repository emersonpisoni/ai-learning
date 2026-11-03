"""
Roda partidas pelo terminal.

    python manage.py simular                        # 1 partida, salva no banco e imprime
    python manage.py simular --seed 42              # partida reproduzível
    python manage.py simular --partidas 500         # estatísticas (só em memória, rápido)
"""

from django.core.management.base import BaseCommand

from game.engine import Team
from game.services import create_match, run_match, win_rates


class Command(BaseCommand):
    help = "Simula partidas de Lobisomem entre agentes."

    def add_arguments(self, parser):
        parser.add_argument("--jogadores", type=int, default=8)
        parser.add_argument("--seed", type=int, default=None)
        parser.add_argument("--partidas", type=int, default=1)
        parser.add_argument("--deus", action="store_true", help="Mostra eventos privados e pensamentos.")

    def handle(self, *args, jogadores, seed, partidas, deus, **options):
        if partidas > 1:
            self._stats(jogadores, partidas, seed or 0)
            return

        match = run_match(create_match(num_players=jogadores, seed=seed))
        self.stdout.write(self.style.MIGRATE_HEADING(f"Partida #{match.pk} (seed {match.seed})"))
        for p in match.players.all():
            self.stdout.write(f"  {p.name:<8} {p.get_role_display()}")
        self.stdout.write("")

        for e in match.events.all():
            if not e.is_public and not deus:
                continue
            prefix = "  🔒 " if not e.is_public else "  "
            line = f"{prefix}{e.actor + ': ' if e.kind == 'fala' else ''}{e.content}"
            self.stdout.write(self.style.WARNING(line) if e.kind == "fase" else line)
            if deus and e.thought:
                self.stdout.write(self.style.HTTP_INFO(f"      💭 {e.thought}"))

    def _stats(self, jogadores, partidas, first_seed):
        results = win_rates(jogadores, partidas, first_seed)
        self.stdout.write(self.style.MIGRATE_HEADING(f"{partidas} partidas com {jogadores} jogadores"))
        for label, key in [("🏡 Aldeia", Team.VILLAGE), ("🐺 Lobos", Team.WOLVES), ("⏳ Empate", None)]:
            n = results.get(key, 0)
            bar = "█" * round(40 * n / partidas)
            self.stdout.write(f"  {label:<10} {n:>5}  {100 * n / partidas:5.1f}%  {bar}")
