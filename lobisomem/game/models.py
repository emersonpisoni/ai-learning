from django.db import models
from django.urls import reverse

from .engine import EventKind, Phase, Role, Team


class Match(models.Model):
    """Uma partida de Lobisomem."""

    class Status(models.TextChoices):
        CREATED = "created", "Criada"
        RUNNING = "running", "Em andamento"
        FINISHED = "finished", "Finalizada"

    created_at = models.DateTimeField(auto_now_add=True)
    seed = models.PositiveIntegerField(help_text="Mesma seed = mesma partida (ótimo para debugar).")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    winner = models.CharField(max_length=20, choices=[(t.value, t.value.title()) for t in Team], blank=True)
    rounds_played = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "partida"

    def __str__(self) -> str:
        return f"Partida #{self.pk}"

    def get_absolute_url(self) -> str:
        return reverse("game:detail", args=[self.pk])


class Player(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="players")
    seat = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=40)
    role = models.CharField(max_length=20, choices=[(r.value, r.label) for r in Role])
    alive = models.BooleanField(default=True)
    agent_type = models.CharField(max_length=20, default="random")
    personality = models.TextField(blank=True)

    class Meta:
        ordering = ["seat"]
        constraints = [models.UniqueConstraint(fields=["match", "name"], name="unique_player_name_per_match")]
        verbose_name = "jogador"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_role_display()})"

    @property
    def is_wolf(self) -> bool:
        return self.role == Role.WEREWOLF


class GameEvent(models.Model):
    """Espelho do engine.Event no banco. É a linha do tempo da partida."""

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="events")
    order = models.PositiveIntegerField()
    round = models.PositiveIntegerField()
    phase = models.CharField(max_length=20, choices=[(p.value, p.value) for p in Phase])
    kind = models.CharField(max_length=30, choices=[(k.value, k.value) for k in EventKind])
    actor = models.CharField(max_length=40, blank=True)
    target = models.CharField(max_length=40, blank=True)
    content = models.TextField()
    visibility = models.CharField(max_length=40, default="public")
    thought = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]
        constraints = [models.UniqueConstraint(fields=["match", "order"], name="unique_event_order")]
        verbose_name = "evento"

    def __str__(self) -> str:
        return f"[{self.round}/{self.phase}] {self.content[:60]}"

    @property
    def is_public(self) -> bool:
        return self.visibility == "public"
