from django import template

register = template.Library()

@register.filter
def subtract(value, arg):
    try:
        return (value or 0) - (arg or 0)
    except (TypeError, ValueError):
        return 0
