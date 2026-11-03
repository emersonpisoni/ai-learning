"""
Roda partidas pelo terminal.

    python manage.py simular                        # 1 partida com agentes aleatórios
    python manage.py simular --seed 42 --deus       # mostra segredos e pensamentos
    python manage.py simular --agente llm --deus    # partida com IA (precisa do .env)
    python manage.py simular --agente misto         # metade IA, metade aleatórios
    python manage.py simular --partidas 500         # estatísticas (aleatórios, em memória)
"""

from django.core.management.base import BaseCommand, CommandError

from game.engine import Event, EventKind, Team
from game.services import AGENT_MODES, create_match, run_match, win_rates


class Command(BaseCommand):
    help = "Simula partidas de Lobisomem entre agentes."

    def add_arguments(self, parser):
        parser.add_argument("--jogadores", type=int, default=8)
        parser.add_argument("--seed", type=int, default=None)
        parser.add_argument("--partidas", type=int, default=1)
        parser.add_argument("--agente", choices=list(AGENT_MODES), default="random")
        parser.add_argument("--deus", action="store_true", help="Mostra eventos privados e pensamentos.")

    def handle(self, *args, jogadores, seed, partidas, agente, deus, **options):
        if partidas > 1:
            if agente != "random":
                raise CommandError("Estatísticas com várias partidas só com agentes aleatórios, por enquanto.")
            self._stats(jogadores, partidas, seed or 0)
            return

        match = create_match(num_players=jogadores, seed=seed, agent_mode=agente)
        self.stdout.write(self.style.MIGRATE_HEADING(f"Partida #{match.pk} (seed {match.seed})"))
        for p in match.players.all():
            bot = "🤖" if p.agent_type == "llm" else "  "
            extra = f"  · {p.personality}" if deus and p.personality else ""
            self.stdout.write(f"  {bot} {p.name:<8} {p.get_role_display():<10}{extra}")
        self.stdout.write("")

        # Imprime cada evento no momento em que acontece.
        match = run_match(match, on_event=lambda e: self._print_event(e, deus))
        if match.status == match.Status.ERROR:
            raise CommandError(match.error)

    def _print_event(self, e: Event, deus: bool) -> None:
        public = e.visibility == "public"
        if not public and not deus:
            return
        prefix = "  🔒 " if not public else "  "
        line = f"{prefix}{e.actor + ': ' if e.kind is EventKind.SPEECH else ''}{e.content}"
        self.stdout.write(self.style.WARNING(line) if e.kind is EventKind.PHASE else line)
        if deus and e.thought:
            self.stdout.write(self.style.HTTP_INFO(f"      💭 {e.thought}"))

    def _stats(self, jogadores, partidas, first_seed):
        results = win_rates(jogadores, partidas, first_seed)
        self.stdout.write(self.style.MIGRATE_HEADING(f"{partidas} partidas com {jogadores} jogadores"))
        for label, key in [("🏡 Aldeia", Team.VILLAGE), ("🐺 Lobos", Team.WOLVES), ("⏳ Empate", None)]:
            n = results.get(key, 0)
            bar = "█" * round(40 * n / partidas)
            self.stdout.write(f"  {label:<10} {n:>5}  {100 * n / partidas:5.1f}%  {bar}")
