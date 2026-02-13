from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .services.ai_recommender import get_deck_recommendations
from .services.scryfall import ScryfallService


def _get_card_data(name):
    """Return card details from Scryfall for a card name, or None."""
    if not name or not name.strip():
        return None
    card = ScryfallService.get_card_by_name(name.strip())
    if not card:
        return None
    
    uris = card.get("image_uris") or {}
    image_url = uris.get("normal") or uris.get("large") or uris.get("small")
    
    # Handle double-faced cards if root image_uris is missing
    if not image_url and "card_faces" in card:
        image_url = card["card_faces"][0].get("image_uris", {}).get("normal")

    return {
        "name": card.get("name"),
        "image_url": image_url,
        "type_line": card.get("type_line"),
        "oracle_text": card.get("oracle_text", ""),
    }


@login_required(login_url='login')
def recommendations(request):
    recs = []
    if request.method == "POST":
        format_name = request.POST.get("format")
        colors = request.POST.getlist("colors")
        card_names = get_deck_recommendations(format_name, colors)
        
        for name in card_names:
            data = _get_card_data(name)
            if data:
                # Structure as a 'deck' object for the template
                recs.append({
                    "title": data["name"],
                    "theme": data["type_line"],  # Show type as theme
                    "commander": None,           # No specific commander needed for single card
                    "commander_image_url": data["image_url"], # Use main image slot
                    "description": data["oracle_text"],
                    "key_cards": []
                })
            
    return render(request, "card_recommender/recommendations.html", {"recommendations": recs})
