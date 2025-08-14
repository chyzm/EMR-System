# utils.py
from datetime import timedelta
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from .models import ActionLog

def log_action(request, action, obj=None, details=""):
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
    """
    Log LOGIN only when a clinic is known.
    If clinic isn't known yet, mark as pending and return.
    Also dedupe in a short window to avoid double-logs.
    """
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
    """
    If a login happened before clinic was known, call this AFTER clinic is set.
    """
    if request.session.pop('__pending_login__', None) and request.user.is_authenticated:
        # Now a clinic should exist in session — this will actually write the row.
        log_login(request, request.user)

def log_logout(request, user):
    ActionLog.objects.create(
        user=user,
        clinic_id=request.session.get('clinic_id'),
        action='LOGOUT',
        details=f"User {user.username} logged out"
    )

    
    
# from django.contrib.contenttypes.models import ContentType
# from .models import ActionLog

# def log_action(request, action, obj=None, details=""):
#     """
#     Creates an ActionLog entry.

#     Args:
#         request: Django request object (used for user and clinic).
#         action (str): One of 'CREATE', 'UPDATE', 'DELETE', 'LOGIN', 'LOGOUT'.
#         obj (model instance, optional): The object related to the action.
#         details (str, optional): Additional description of the action.
#     """
#     clinic_id = request.session.get('clinic_id')

#     ActionLog.objects.create(
#         user=request.user if request.user.is_authenticated else None,
#         clinic_id=clinic_id,
#         action=action,
#         content_type=ContentType.objects.get_for_model(obj) if obj else None,
#         object_id=getattr(obj, 'pk', None) if obj else None,  # ✅ Use pk instead of id
#         details=details
#     )

    
    
# def log_login(request, user):
#     """Log user login action with session or fallback clinic"""
#     clinic_id = request.session.get('clinic_id')

#     # Fallback if session clinic_id is not yet set
#     if not clinic_id and hasattr(user, 'primary_clinic') and user.primary_clinic:
#         clinic_id = user.primary_clinic.id

#     ActionLog.objects.create(
#         user=user,
#         clinic_id=clinic_id,
#         action='LOGIN',
#         details=f"User {user.get_full_name() or user.username} logged in"
#     )


# def log_logout(request, user):
#     """Log user logout action"""
#     ActionLog.objects.create(
#         user=user,
#         clinic_id=request.session.get('clinic_id'),
#         action='LOGOUT',
#         details=f"User {user.username} logged out"
#     )


