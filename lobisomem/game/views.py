from itertools import groupby

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Match
from .services import create_match, run_match


def index(request):
    matches = Match.objects.prefetch_related("players")[:30]
    return render(request, "game/index.html", {"matches": matches})


@require_POST
def new_match(request):
    try:
        num_players = int(request.POST.get("num_players", 8))
        seed_raw = request.POST.get("seed", "").strip()
        seed = int(seed_raw) if seed_raw else None
        match = create_match(num_players=num_players, seed=seed)
    except ValueError as exc:
        messages.error(request, str(exc) or "Valores inválidos.")
        return redirect("game:index")

    run_match(match)
    return redirect(match)


def detail(request, pk: int):
    match = get_object_or_404(Match.objects.prefetch_related("players"), pk=pk)
    events = list(match.events.all())
    rounds = [(rnd, list(evts)) for rnd, evts in groupby(events, key=lambda e: e.round)]
    return render(
        request,
        "game/detail.html",
        {"match": match, "players": match.players.all(), "rounds": rounds},
    )
