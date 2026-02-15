"""
Utility to organize cards by type and fetch card details from S3.
"""

from typing import Dict, List
from functools import lru_cache
import logging
from .scryfall_s3_service import ScryfallS3Service

logger = logging.getLogger(__name__)


# Global cache for all cards (loaded once)
_cards_cache = None
_cards_index = None  # Dictionary for O(1) lookup
_scryfall_service = None


def _get_all_cards_cached():
    """Load all cards from S3 once and cache them with an index."""
    global _cards_cache, _cards_index, _scryfall_service
    if _cards_cache is None:
        _scryfall_service = ScryfallS3Service()
        _cards_cache = _scryfall_service.get_all_cards()
        
        # Build index for O(1) lookups
        _cards_index = {}
        for card in _cards_cache:
            card_name = card.get('name', '').lower().strip()
            if card_name:
                _cards_index[card_name] = card
    
    return _cards_cache


def _find_card_in_cache(card_name: str) -> Dict:
    """Find a card in the cached data by name using O(1) index lookup.
    
    Tries exact match first, then fuzzy match if needed.
    """
    _get_all_cards_cached()  # Ensure cache and index are loaded
    global _cards_index
    
    card_name_lower = card_name.lower().strip()
    
    # First try exact match using index (O(1))
    if card_name_lower in _cards_index:
        return _cards_index[card_name_lower]
    
    # Try match without special characters (e.g., "Æ" → "A")
    import unicodedata
    normalized_search = unicodedata.normalize('NFD', card_name_lower)
    normalized_search = ''.join(c for c in normalized_search if unicodedata.category(c) != 'Mn')
    
    # Try normalized lookup in index
    if normalized_search in _cards_index:
        return _cards_index[normalized_search]
    
    # Fallback: Try fuzzy match (only if exact fails)
    for indexed_name, card in _cards_index.items():
        # Check if card name is contained in search or similar
        if (card_name_lower in indexed_name or indexed_name in card_name_lower or
            _string_similarity(card_name_lower, indexed_name) > 0.85):
            return card
    
    return None


def _string_similarity(a: str, b: str) -> float:
    """Simple string similarity score using Levenshtein-like logic."""
    if a == b:
        return 1.0
    if len(a) == 0 or len(b) == 0:
        return 0.0
    
    # Count matching characters
    matches = sum(1 for i, c in enumerate(a) if i < len(b) and c == b[i])
    return matches / max(len(a), len(b))


def get_card_type_category(type_line: str) -> str:
    """
    Categorize a Magic card by its primary type.
    
    Args:
        type_line: Card type line (e.g., "Land — Mountain", "Sorcery", "Creature — Goblin")
    
    Returns:
        Category: 'Creature', 'Sorcery', 'Instant', 'Enchantment', 'Artifact', 'Planeswalker', 'Land', 'Other'
    """
    type_line_lower = type_line.lower()
    
    if 'creature' in type_line_lower:
        return 'Creature'
    elif 'sorcery' in type_line_lower:
        return 'Sorcery'
    elif 'instant' in type_line_lower:
        return 'Instant'
    elif 'enchantment' in type_line_lower:
        return 'Enchantment'
    elif 'planeswalker' in type_line_lower:
        return 'Planeswalker'
    elif 'artifact' in type_line_lower:
        return 'Artifact'
    elif 'land' in type_line_lower:
        return 'Land'
    else:
        return 'Other'


def organize_cards_by_type(cards_data: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Organize cards by their type category.
    Fetches card details from cached S3 data for performance.
    
    Args:
        cards_data: List of card dicts with 'card_name', 'quantity', etc.
    
    Returns:
        Dict with type categories as keys and list of cards as values
    """
    organized = {}
    
    for card_info in cards_data:
        card_name = card_info.get('card_name')
        
        # Fetch card from cache (not from S3 each time)
        card_data = _find_card_in_cache(card_name)
        
        if not card_data:
            # If not found in cache, use placeholder
            logger.warning(f"Card not found in Scryfall database: {card_name}")
            category = 'Unknown'
            card_with_details = {
                **card_info,
                'type_line': f'(Not found in database - search for "{card_name}")',
                'image_url': None,
                'mana_cost': '',
                'oracle_text': '',
                'price': 0.0,
            }
        else:
            category = get_card_type_category(card_data.get('type_line', ''))
            
            # Extract price (default to 0 if not available)
            prices = card_data.get('prices', {})
            usd_price = prices.get('usd')
            
            try:
                if usd_price is None or usd_price == '':
                    usd_price = 0.0
                else:
                    usd_price = float(usd_price)
            except (ValueError, TypeError):
                usd_price = 0.0
            
            card_with_details = {
                **card_info,
                'type_line': card_data.get('type_line', ''),
                'image_url': ScryfallS3Service.get_card_image_url(card_data, 'normal'),
                'mana_cost': card_data.get('mana_cost', ''),
                'oracle_text': card_data.get('oracle_text', ''),
                'colors': card_data.get('colors', []),
                'price': usd_price,
            }
        
        if category not in organized:
            organized[category] = []
        
        organized[category].append(card_with_details)
    
    # Sort categories in a logical order
    type_order = ['Land', 'Creature', 'Sorcery', 'Instant', 'Enchantment', 'Artifact', 'Planeswalker', 'Other', 'Unknown']
    sorted_organized = {}
    for type_cat in type_order:
        if type_cat in organized:
            sorted_organized[type_cat] = sorted(organized[type_cat], key=lambda x: x['card_name'])
    
    return sorted_organized


def clear_cache():
    """Clear the cards cache (useful for testing or manual refresh)."""
    global _cards_cache, _cards_index
    _cards_cache = None
    _cards_index = None


def get_deck_metadata(cards_data: List[Dict]) -> Dict:
    """
    Lightweight function to get deck color identity and representative card.
    Much faster than organize_cards_by_type() for deck list views.
    
    Args:
        cards_data: List of card dicts with 'card_name', 'quantity', etc.
    
    Returns:
        Dict with 'colors' (list) and 'representative_image' (str or None)
    """
    colors = set()
    representative_card = None
    highest_price = 0
    is_creature = False
    
    for card_info in cards_data:
        card_name = card_info.get('card_name')
        card_data = _find_card_in_cache(card_name)
        
        if not card_data:
            continue
        
        # Collect colors
        card_colors = card_data.get('colors', [])
        if card_colors:
            colors.update(card_colors)
        
        # Find representative card (prefer creatures, then highest price non-land)
        image_url = ScryfallS3Service.get_card_image_url(card_data, 'normal')
        if not image_url:
            continue
        
        type_line = card_data.get('type_line', '').lower()
        is_land = 'land' in type_line
        is_card_creature = 'creature' in type_line
        
        # Skip lands for representative card
        if is_land:
            continue
        
        # Extract price
        prices = card_data.get('prices', {})
        usd_price = prices.get('usd')
        try:
            card_price = float(usd_price) if usd_price else 0.0
        except (ValueError, TypeError):
            card_price = 0.0
        
        # Select representative card
        if representative_card is None:
            representative_card = image_url
            highest_price = card_price
            is_creature = is_card_creature
        elif is_card_creature and not is_creature:
            # Prefer creatures over non-creatures
            representative_card = image_url
            highest_price = card_price
            is_creature = True
        elif is_card_creature and is_creature and card_price > highest_price:
            # Among creatures, pick highest price
            representative_card = image_url
            highest_price = card_price
        elif not is_creature and not is_card_creature and card_price > highest_price:
            # Among non-creature spells, pick highest price
            representative_card = image_url
            highest_price = card_price
    
    # Sort colors in WUBRG order
    color_order = {'W': 0, 'U': 1, 'B': 2, 'R': 3, 'G': 4}
    sorted_colors = sorted(list(colors), key=lambda c: color_order.get(c, 5))
    
    return {
        'colors': sorted_colors,
        'representative_image': representative_card
    }
