from django import template
from django.utils import timezone

register = template.Library()

@register.filter
def filter_expiry(queryset, urgency_level):
    today = timezone.now().date()
    
    if urgency_level == 'critical':
        return [m for m in queryset if (m.expiry_date - today).days <= 7]
    elif urgency_level == 'high':
        return [m for m in queryset if 8 <= (m.expiry_date - today).days <= 14]
    elif urgency_level == 'medium':
        return [m for m in queryset if 15 <= (m.expiry_date - today).days <= 21]
    elif urgency_level == 'low':
        return [m for m in queryset if 22 <= (m.expiry_date - today).days <= 30]
    return queryset