from django import template

register = template.Library()

@register.filter
def subtract(value, arg):
    return value - arg

@register.filter
def currency(value):
    return f"₦{value:,.2f}"