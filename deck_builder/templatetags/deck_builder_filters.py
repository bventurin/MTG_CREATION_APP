from django import template
import re

register = template.Library()


@register.filter
def mul(value, arg):
    """Multiply value by arg."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def mana_icons(mana_cost_text):
    """Convert mana cost text (e.g., '3UGG') to HTML with mana-font icons.
    
    Uses the mana-font CDN library (https://github.com/andrewgioia/mana)
    """
    if not mana_cost_text:
        return ''
    
    mana_cost_text = str(mana_cost_text).strip()
    if not mana_cost_text:
        return ''
    
    # Mapping of mana symbols to mana-font icon classes
    mana_map = {
        'W': '<i class="ms ms-w ms-cost ms-shadow"></i>',
        'U': '<i class="ms ms-u ms-cost ms-shadow"></i>',
        'B': '<i class="ms ms-b ms-cost ms-shadow"></i>',
        'R': '<i class="ms ms-r ms-cost ms-shadow"></i>',
        'G': '<i class="ms ms-g ms-cost ms-shadow"></i>',
        'C': '<i class="ms ms-c ms-cost ms-shadow"></i>',
        'X': '<i class="ms ms-x ms-cost ms-shadow"></i>',
    }
    
    result = ''
    i = 0
    while i < len(mana_cost_text):
        char = mana_cost_text[i]
        
        # Check for two-digit numbers
        if i + 1 < len(mana_cost_text) and char.isdigit() and mana_cost_text[i + 1].isdigit():
            two_digit = char + mana_cost_text[i + 1]
            result += f'<i class="ms ms-{two_digit} ms-cost ms-shadow"></i>'
            i += 2
        elif char.isdigit():
            result += f'<i class="ms ms-{char} ms-cost ms-shadow"></i>'
            i += 1
        elif char.upper() in mana_map:
            result += mana_map[char.upper()]
            i += 1
        else:
            # Skip unknown characters
            i += 1
    
    return f'<span class="mana-cost">{result}</span>'


@register.filter
def mark_safe_mana(value):
    """Mark mana icons as safe HTML."""
    from django.utils.safestring import mark_safe
    return mark_safe(value)
