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
#         object_id=obj.id if obj else None,
#         details=details
#     )
    
    
from django.contrib.contenttypes.models import ContentType
from .models import ActionLog

def log_action(request, action, obj=None, details=""):
    """
    Creates an ActionLog entry.

    Args:
        request: Django request object (used for user and clinic).
        action (str): One of 'CREATE', 'UPDATE', 'DELETE', 'LOGIN', 'LOGOUT'.
        obj (model instance, optional): The object related to the action.
        details (str, optional): Additional description of the action.
    """
    clinic_id = request.session.get('clinic_id')

    ActionLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        clinic_id=clinic_id,
        action=action,
        content_type=ContentType.objects.get_for_model(obj) if obj else None,
        object_id=getattr(obj, 'pk', None) if obj else None,  # ✅ Use pk instead of id
        details=details
    )


