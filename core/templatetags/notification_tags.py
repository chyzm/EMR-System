# core/templatetags/notification_tags.py
from django import template
from django.db.models import Q
from core.models import Notification, NotificationRead

register = template.Library()

@register.simple_tag
def get_unread_notifications(user, clinic_id, app_name=None):
    if not clinic_id:
        return Notification.objects.none()
    
    read_global_ids = NotificationRead.objects.filter(user=user).values_list('notification_id', flat=True)
    
    query = (
        Q(user=user, clinic_id=clinic_id) | 
        Q(user__isnull=True, clinic_id=clinic_id)
    )
    
    if app_name:
        query &= Q(app_name=app_name)
    
    return Notification.objects.filter(
        query,
        is_read=False
    ).exclude(id__in=read_global_ids)

@register.filter
def has_unread_notifications(user, clinic_id):
    if not clinic_id:
        return False
    
    read_global_ids = NotificationRead.objects.filter(user=user).values_list('notification_id', flat=True)
    return Notification.objects.filter(
        (Q(user=user) | Q(user__isnull=True, clinic_id=clinic_id)),
        is_read=False
    ).exclude(id__in=read_global_ids).exists()