from django import template

register = template.Library()

@register.filter
def mul(value, arg):
    """Multiply two numbers"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0




@register.filter
def subtract(value, arg):
    """Subtract arg from value."""
    try:
        from decimal import Decimal
        return Decimal(str(value or 0)) - Decimal(str(arg or 0))
    except (ValueError, TypeError):
        return 0

@register.filter
def add_filter(value, arg):
    """Add arg to value."""
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def multiply(value, arg):
    """Multiply value by arg."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def divide(value, arg):
    """Divide value by arg."""
    try:
        return float(value) / float(arg) if float(arg) != 0 else 0
    except (ValueError, TypeError):
        return 0


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key."""
    if dictionary is None:
        return None
    return dictionary.get(key)
