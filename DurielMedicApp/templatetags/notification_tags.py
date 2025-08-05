from django import template
from ..models import Notification

register = template.Library()

@register.filter(name='unread_notifications')
def unread_notifications(user):
    return user.notifications.filter(is_read=False)