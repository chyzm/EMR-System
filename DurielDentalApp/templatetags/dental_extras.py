from django import template

register = template.Library()


@register.filter
def get_attr(obj, attr):
    value = getattr(obj, attr, '')
    if callable(value):
        value = value()
    return value
