from django.shortcuts import render
from .services.ai_recommender import get_deck_recommendations
from .services.scryfall import ScryfallService


def _image_url_for_card_name(name):
    """Return image URL from Scryfall for a card name, or None."""
    if not name or not name.strip():
        return None
    card = ScryfallService.get_card_by_name(name.strip())
    if not card:
        return None
    uris = card.get("image_uris") or {}
    return uris.get("normal") or uris.get("small") or uris.get("large")


def _enrich_deck_with_images(deck, max_key_cards=6):
    """Add commander_image_url and key_cards_with_images to a deck dict."""
    deck = dict(deck)
    deck["commander_image_url"] = None
    deck["key_cards_with_images"] = []

    if deck.get("commander"):
        deck["commander_image_url"] = _image_url_for_card_name(deck["commander"])

    for name in (deck.get("key_cards") or [])[:max_key_cards]:
        url = _image_url_for_card_name(name)
        deck["key_cards_with_images"].append({"name": name, "image_url": url})

    return deck


def recommendations(request):
    recs = []
    if request.method == "POST":
        format_name = request.POST.get("format")
        colors = request.POST.getlist("colors")
        recs = get_deck_recommendations(format_name, colors)
        recs = [_enrich_deck_with_images(d) for d in recs]
    return render(request, "card_recommender/recommendations.html", {"recommendations": recs})
