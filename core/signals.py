from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from crum import get_current_request
from .models import ActionLog

@receiver(post_save)
def log_save_action(sender, instance, created, **kwargs):
    if sender is ActionLog:
        return
    
    if sender.__name__ in ["Session", "ContentType", "Permission", "Group"]:
        return
    
    # 🚫 Skip system-driven CustomUser updates like last_login
    if sender.__name__ == "CustomUser" and not created:
        update_fields = kwargs.get('update_fields', None)
        if update_fields and update_fields == {'last_login'}:
            return
        # Extra safety: if no request or no real field changes, skip
        request = get_current_request()
        if not request:
            return

    request = get_current_request()
    clinic = None
    user = None

    # ✅ Prefer clinic from current request session
    if request and request.user.is_authenticated:
        # 🚫 Skip if superuser
        if request.user.is_superuser:
            return

        clinic_id = request.session.get('clinic_id')
        if clinic_id:
            try:
                from .models import Clinic
                clinic = Clinic.objects.get(id=clinic_id)
            except Clinic.DoesNotExist:
                clinic = None
        user = request.user

    # 🚫 Remove the M2M fallback for CustomUser — prevents cross-clinic bleed
    if not clinic and hasattr(instance, 'clinic') and sender.__name__ != "CustomUser":
        clinic_attr = getattr(instance, 'clinic', None)
        if clinic_attr:
            if hasattr(clinic_attr, 'first'):
                clinic = clinic_attr.first()
            elif hasattr(clinic_attr, 'pk'):
                clinic = clinic_attr

    if not user:
        user = getattr(instance, 'created_by', None) or getattr(instance, 'last_modified_by', None)

    # ✅ Only log if we have a clinic context and a meaningful user
    if clinic and user:
        try:
            ActionLog.objects.create(
                user=user,
                clinic=clinic,
                action='CREATE' if created else 'UPDATE',
                content_type=ContentType.objects.get_for_model(instance),
                object_id=getattr(instance, 'pk', None),
                details=f"{instance.__class__.__name__} {'created' if created else 'updated'}"
            )
        except Exception:
            pass


@receiver(post_delete)
def log_delete_action(sender, instance, **kwargs):
    if sender.__name__ in ["ActionLog", "Session", "ContentType", "Permission", "Group"]:
        return
    
    if hasattr(instance, '_state') and getattr(instance._state, 'adding', False):
        return
    
    request = get_current_request()
    
    if not request or not request.user.is_authenticated:
        return

    # 🚫 Skip if superuser
    if request.user.is_superuser:
        return
    
    clinic = None
    user = request.user
    
    clinic_id = request.session.get('clinic_id')
    if clinic_id:
        try:
            from .models import Clinic
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            clinic = None
    
    if not clinic and hasattr(instance, 'clinic'):
        clinic_attr = getattr(instance, 'clinic', None)
        if clinic_attr:
            if hasattr(clinic_attr, 'first'):
                clinic = clinic_attr.first()
            elif hasattr(clinic_attr, 'pk'):
                clinic = clinic_attr
    
    if not user:
        user = getattr(instance, 'created_by', None) or getattr(instance, 'last_modified_by', None)
    
    if clinic:
        try:
            ActionLog.objects.create(
                user=user,
                clinic=clinic,
                action='DELETE',
                content_type=ContentType.objects.get_for_model(instance),
                object_id=instance.pk,
                details=f"{instance.__class__.__name__} deleted"
            )
        except Exception:
            pass


from django.contrib.auth.signals import user_login_failed

@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    try:
        # 🚫 Skip logging failed login for superuser username
        if credentials.get('username') and hasattr(request, 'user') and request.user.is_superuser:
            return

        ActionLog.objects.create(
            user=None,
            clinic_id=request.session.get('clinic_id'),
            action='LOGIN_FAILED',
            details=f"Failed login attempt for username: {credentials.get('username')}"
        )
    except Exception:
        pass
