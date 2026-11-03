from itertools import groupby

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from .models import Match
from .services import AGENT_MODES, create_match, run_match, run_match_in_background


def index(request):
    matches = Match.objects.prefetch_related("players")[:30]
    return render(request, "game/index.html", {"matches": matches, "agent_modes": AGENT_MODES})


@require_POST
def new_match(request):
    try:
        num_players = int(request.POST.get("num_players", 8))
        seed_raw = request.POST.get("seed", "").strip()
        seed = int(seed_raw) if seed_raw else None
        agent_mode = request.POST.get("agent_mode", "random")
        match = create_match(num_players=num_players, seed=seed, agent_mode=agent_mode)
    except ValueError as exc:
        messages.error(request, str(exc) or "Valores inválidos.")
        return redirect("game:index")

    if match.uses_llm:
        # Com IA a partida leva minutos: roda em segundo plano e a página acompanha.
        run_match_in_background(match.pk)
    else:
        run_match(match)
    return redirect(match)


def _live_context(pk: int) -> dict:
    match = get_object_or_404(Match.objects.prefetch_related("players"), pk=pk)
    events = list(match.events.all())
    rounds = [(rnd, list(evts)) for rnd, evts in groupby(events, key=lambda e: e.round)]
    return {"match": match, "players": match.players.all(), "rounds": rounds, "event_count": len(events)}


def detail(request, pk: int):
    return render(request, "game/detail.html", _live_context(pk))


def live(request, pk: int):
    """
    Endpoint que o JS da página consulta a cada poucos segundos (polling).
    Devolve o HTML atualizado da partida. Na etapa 4 isso vira WebSocket.
    """
    context = _live_context(pk)
    return JsonResponse({
        "status": context["match"].status,
        "events": context["event_count"],
        "html": render_to_string("game/_live.html", context, request),
    })
