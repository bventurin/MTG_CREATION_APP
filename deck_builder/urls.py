from django.urls import path, include
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/", include("accounts.urls")),
    path("decks/", views.deck_list, name="deck_list"),
    path("decks/create/", views.create_deck, name="create_deck"),
    path("decks/<uuid:deck_id>/", views.deck_detail, name="deck_detail"),
    path("decks/<uuid:deck_id>/edit/", views.edit_deck, name="edit_deck"),
    path("decks/<uuid:deck_id>/delete/", views.delete_deck, name="delete_deck"),
    path(
        "decks/<uuid:deck_id>/recommendations/",
        views.get_recommendations,
        name="get_recommendations",
    ),
    path(
        "decks/<uuid:deck_id>/qr-code/", views.generate_qr_code, name="generate_qr_code"
    ),
    path("decks/<uuid:deck_id>/add-voucher/", views.add_voucher, name="add_voucher"),
    path("decks/<uuid:deck_id>/plot-status/", views.check_plot_status, name="check_plot_status"),
]
