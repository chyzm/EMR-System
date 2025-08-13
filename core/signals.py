from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from crum import get_current_request
from .models import ActionLog

@receiver(post_save)
def log_save_action(sender, instance, created, **kwargs):
    if sender is ActionLog:
        return
    
    request = get_current_request()
    clinic = None
    user = None
    
    if request:
        clinic = getattr(request, 'clinic', None)
        user = getattr(request, 'user', None) if request.user.is_authenticated else None
    
    clinic = clinic or getattr(instance, 'clinic', None)
    user = user or getattr(instance, 'created_by', None) or getattr(instance, 'last_modified_by', None)
    
    if clinic:
        ActionLog.objects.create(
            user=user,
            clinic=clinic,
            action='CREATE' if created else 'UPDATE',
            content_type=ContentType.objects.get_for_model(instance),
            object_id=getattr(instance, 'pk', None),
            details=f"{instance.__class__.__name__} {'created' if created else 'updated'}"
        )

    )

@receiver(post_delete)
def log_delete_action(sender, instance, **kwargs):
    if sender.__name__ == "ActionLog":
        return
    
    from crum import get_current_request
    request = get_current_request()
    
    clinic = None
    user = None
    
    if request:
        clinic = getattr(request, 'clinic', None)
        user = getattr(request, 'user', None)
    
    if not clinic:
        clinic = getattr(instance, 'clinic', None)
    if not user:
        user = getattr(instance, 'created_by', None) or getattr(instance, 'last_modified_by', None)
    
    ActionLog.objects.create(
        user=user,
        clinic=clinic,
        action='DELETE',
        content_type=ContentType.objects.get_for_model(instance),
        object_id=instance.pk,
        details=f"{instance.__class__.__name__} deleted"
    )