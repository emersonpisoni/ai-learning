from django.urls import path

from . import views

app_name = "game"

urlpatterns = [
    path("", views.index, name="index"),
    path("partidas/nova/", views.new_match, name="new"),
    path("partidas/<int:pk>/", views.detail, name="detail"),
]
