from django import template
import re

register = template.Library()


@register.filter
def extract_ipad_variant(name):
    """
    Extract iPad variant type (Air, Mini, Pro, etc.) ignoring numbers.
    If the name only has a number (no variant name), return 'Gen'.

    Examples:
    - 'iPad 1' -> 'Gen'
    - 'iPad 2' -> 'Gen'
    - 'iPad Air 6' -> 'Air'
    - 'iPad Mini 6' -> 'Mini'
    - 'iPad Pro 8' -> 'Pro'
    - 'iPad Air' -> 'Air'
    - 'iPad Pro' -> 'Pro'
    """
    if not name:
        return ''

    # Remove 'iPad' prefix (case-insensitive) using regex
    result = re.sub(r'iPad', '', name, flags=re.IGNORECASE).strip()

    # Extract only the first word (the variant name)
    words = result.split()
    if words:
        variant = words[0]
        # Remove any numbers from the variant name
        variant = ''.join([c for c in variant if not c.isdigit()]).strip()

        # If variant is empty (meaning it was only numbers), return 'Gen'
        if not variant:
            return 'Gen'

        return variant

    return ''


@register.filter
def get_item(dictionary, key):
    """Return dictionary value for key. Accepts int or str keys."""
    if not dictionary:
        return None
    try:
        # Try as-is (int)
        return dictionary.get(key) if hasattr(dictionary, 'get') else None
    except Exception:
        try:
            return dictionary.get(str(key))
        except Exception:
            return None
