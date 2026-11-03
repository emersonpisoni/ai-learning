from django.contrib import admin

from .models import GameEvent, Match, Player


class PlayerInline(admin.TabularInline):
    model = Player
    extra = 0


class GameEventInline(admin.TabularInline):
    model = GameEvent
    extra = 0
    fields = ["order", "round", "phase", "kind", "actor", "target", "content", "visibility", "thought"]
    readonly_fields = fields
    can_delete = False


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ["id", "created_at", "seed", "status", "winner", "rounds_played"]
    list_filter = ["status", "winner"]
    inlines = [PlayerInline, GameEventInline]


@admin.register(GameEvent)
class GameEventAdmin(admin.ModelAdmin):
    list_display = ["match", "order", "round", "phase", "kind", "actor", "target", "visibility"]
    list_filter = ["kind", "phase", "visibility"]
    search_fields = ["content", "thought", "actor"]
