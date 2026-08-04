from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from functools import wraps


def get_active_clinic(request):
    clinic_id = request.session.get('clinic_id')
    if not clinic_id or not request.user.is_authenticated:
        return None

    clinics = request.user.clinic.all()
    if request.user.is_superuser:
        from core.models import Clinic
        clinics = Clinic.objects.all()

    clinic = clinics.filter(pk=clinic_id).first()
    if clinic is None:
        request.session.pop('clinic_id', None)
        request.session.pop('clinic_type', None)
        request.session.pop('clinic_name', None)
    return clinic


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.role not in roles:
                return redirect('DurielMedicApp:dashboard')  # or show permission denied page
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def clinic_selected_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        clinic = getattr(request, 'clinic', None) or get_active_clinic(request)
        if clinic is None:
            return redirect('core:select_clinic')
        request.clinic = clinic
        return view_func(request, *args, **kwargs)
    return _wrapped_view

