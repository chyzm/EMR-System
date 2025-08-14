# utils.py
from datetime import timedelta
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from .models import ActionLog

def log_action(request, action, obj=None, details=""):
    # 🚫 Skip logging for superusers
    if request.user.is_authenticated and request.user.is_superuser:
        return
    
    clinic_id = request.session.get('clinic_id')
    ActionLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        clinic_id=clinic_id,
        action=action,
        content_type=ContentType.objects.get_for_model(obj) if obj else None,
        object_id=getattr(obj, 'pk', None) if obj else None,
        details=details
    )

def log_login(request, user):
    # 🚫 Skip logging for superusers
    if user.is_superuser:
        return

    clinic_id = request.session.get('clinic_id') or getattr(user, 'primary_clinic_id', None)

    if clinic_id is None:
        # Defer until clinic is chosen
        request.session['__pending_login__'] = True
        return

    # De-dupe: if we just logged a LOGIN for same user+clinic in last 10s, skip
    window_start = timezone.now() - timedelta(seconds=10)
    if ActionLog.objects.filter(
        user=user, action='LOGIN', clinic_id=clinic_id, timestamp__gte=window_start
    ).exists():
        return

    ActionLog.objects.create(
        user=user,
        clinic_id=clinic_id,
        action='LOGIN',
        details=f"User {user.get_full_name() or user.username} logged in"
    )

def finalize_pending_login(request):
    if request.session.pop('__pending_login__', None) and request.user.is_authenticated:
        log_login(request, request.user)

def log_logout(request, user):
    # 🚫 Skip logging for superusers
    if user.is_superuser:
        return

    ActionLog.objects.create(
        user=user,
        clinic_id=request.session.get('clinic_id'),
        action='LOGOUT',
        details=f"User {user.username} logged out"
    )
