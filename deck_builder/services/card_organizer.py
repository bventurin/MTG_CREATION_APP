from typing import Dict, List
import logging
from .scryfall_s3_service import ScryfallS3Service

logger = logging.getLogger(__name__)


def get_card_type_category(type_line: str) -> str:
    # Categorize a Magic card by its primary type.
    type_line_lower = type_line.lower()

    if "creature" in type_line_lower:
        return "Creature"
    elif "sorcery" in type_line_lower:
        return "Sorcery"
    elif "instant" in type_line_lower:
        return "Instant"
    elif "enchantment" in type_line_lower:
        return "Enchantment"
    elif "planeswalker" in type_line_lower:
        return "Planeswalker"
    elif "artifact" in type_line_lower:
        return "Artifact"
    elif "land" in type_line_lower:
        return "Land"
    else:
        return "Other"


def organize_cards_by_type(cards_data: List[Dict]) -> Dict[str, List[Dict]]:
    # Organize cards by their type category.
    scryfall_service = ScryfallS3Service()
    organized = {}

    for card_info in cards_data:
        card_name = card_info.get("card_name")
        card_data = scryfall_service.get_card_by_name(card_name)

        if not card_data:
            logger.warning(f"Card not found in Scryfall database: {card_name}")
            category = "Unknown"
            card_with_details = {
                **card_info,
                "type_line": f'(Not found in database - search for "{card_name}")',
                "image_url": None,
                "mana_cost": "",
                "oracle_text": "",
                "price": 0.0,
            }
        else:
            category = get_card_type_category(card_data.get("type_line", ""))

            # Extract price with fallback
            usd_price = ScryfallS3Service.get_card_price(card_data)

            # Get mana_cost with card_faces fallback for multiface cards
            mana_cost = ScryfallS3Service.get_card_mana_cost(card_data)

            card_with_details = {
                **card_info,
                "type_line": card_data.get("type_line", ""),
                "image_url": ScryfallS3Service.get_card_image_url(card_data, "normal"),
                "mana_cost": mana_cost,
                "oracle_text": card_data.get("oracle_text", ""),
                "colors": card_data.get("colors", []),
                "price": usd_price,
            }

        if category not in organized:
            organized[category] = []

        organized[category].append(card_with_details)

    # Sort categories in a logical order
    type_order = [
        "Land",
        "Creature",
        "Sorcery",
        "Instant",
        "Enchantment",
        "Artifact",
        "Planeswalker",
        "Other",
        "Unknown",
    ]
    sorted_organized = {}
    for type_cat in type_order:
        if type_cat in organized:
            sorted_organized[type_cat] = sorted(
                organized[type_cat], key=lambda x: x["card_name"]
            )

    return sorted_organized


def _should_update_representative(
    representative_card, is_creature: bool, is_card_creature: bool,
    card_price: float, highest_price: float
) -> bool:
    """Return True if the current card should replace the representative image."""
    if representative_card is None:
        return True
    if is_card_creature and not is_creature:
        return True
    if is_card_creature and is_creature and card_price > highest_price:
        return True
    return not is_creature and not is_card_creature and card_price > highest_price


def get_deck_metadata(cards_data: List[Dict]) -> Dict:
    scryfall_service = ScryfallS3Service()
    colors = set()
    representative_card = None
    highest_price = 0
    is_creature = False

    for card_info in cards_data:
        card_name = card_info.get("card_name")
        card_data = scryfall_service.get_card_by_name(card_name, allow_api_fallback=False)

        if not card_data:
            continue

        card_colors = card_data.get("colors", [])
        if card_colors:
            colors.update(card_colors)

        image_url = ScryfallS3Service.get_card_image_url(card_data, "normal")
        if not image_url:
            continue

        type_line = card_data.get("type_line", "").lower()
        is_land = "land" in type_line
        is_card_creature = "creature" in type_line

        # Skip lands for representative card
        if is_land:
            continue

        # Extract price with fallback
        card_price = ScryfallS3Service.get_card_price(card_data)

        # Select representative card
        if _should_update_representative(representative_card, is_creature, is_card_creature, card_price, highest_price):
            representative_card = image_url
            highest_price = card_price
            is_creature = is_card_creature

    # Sort colors in WUBRG order
    color_order = {"W": 0, "U": 1, "B": 2, "R": 3, "G": 4}
    sorted_colors = sorted(list(colors), key=lambda c: color_order.get(c, 5))

    return {"colors": sorted_colors, "representative_image": representative_card}
