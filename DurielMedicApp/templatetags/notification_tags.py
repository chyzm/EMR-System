from django import template
from ..models import Notification

register = template.Library()

@register.filter(name='unread_notifications')
def unread_notifications(user):
    return user.notifications.filter(is_read=False)



from django import template
from ..models import Notification, NotificationRead
from django.db.models import Q

register = template.Library()

@register.simple_tag
def get_unread_notifications(user, clinic_id):
    if not clinic_id:
        return Notification.objects.none()
    
    read_global_ids = NotificationRead.objects.filter(user=user).values_list('notification_id', flat=True)
    return Notification.objects.filter(
        (Q(user=user) | Q(user__isnull=True, clinic_id=clinic_id)),
        is_read=False
    ).exclude(id__in=read_global_ids)
    
    
from django import template
from django.db.models import Q
from ..models import Notification, NotificationRead

register = template.Library()

@register.simple_tag
def get_unread_notifications(user, clinic_id):
    """Simple tag version that returns the queryset"""
    if not clinic_id:
        return Notification.objects.none()
    
    read_global_ids = NotificationRead.objects.filter(user=user).values_list('notification_id', flat=True)
    return Notification.objects.filter(
        (Q(user=user) | Q(user__isnull=True, clinic_id=clinic_id)),
        is_read=False
    ).exclude(id__in=read_global_ids)

@register.filter
def has_unread_notifications(user, clinic_id):
    """Filter version that returns boolean"""
    if not clinic_id:
        return False
    
    read_global_ids = NotificationRead.objects.filter(user=user).values_list('notification_id', flat=True)
    return Notification.objects.filter(
        (Q(user=user) | Q(user__isnull=True, clinic_id=clinic_id)),
        is_read=False
    ).exclude(id__in=read_global_ids).exists()