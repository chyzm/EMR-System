from django.contrib import messages
from django.shortcuts import redirect

from core.decorators import clinic_subscription_is_expired, get_active_clinic


SUBSCRIPTION_EXEMPT_PATH_PREFIXES = (
    '/login/',
    '/logout/',
    '/select-clinic/',
    '/plans/',
    '/register/',
    '/subscribe/',
    '/paystack/',
    '/password-reset/',
    '/reset/',
    '/api/server-sync/',
    '/service-worker.js',
    '/static/',
    '/media/',
    '/admin/',
)


def _clear_clinic_session(request):
    request.session.pop('clinic_id', None)
    request.session.pop('clinic_type', None)
    request.session.pop('clinic_name', None)


def _subscription_check_exempt(request):
    path = request.path_info or '/'
    return any(path == prefix.rstrip('/') or path.startswith(prefix) for prefix in SUBSCRIPTION_EXEMPT_PATH_PREFIXES)

class ClinicMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not hasattr(request, 'clinic'):
            request.clinic = get_active_clinic(request)

        if (
            getattr(request, 'user', None)
            and request.user.is_authenticated
            and request.clinic is not None
            and not _subscription_check_exempt(request)
            and clinic_subscription_is_expired(request.clinic)
        ):
            _clear_clinic_session(request)
            messages.warning(request, "This clinic subscription has expired. Please renew to continue.")
            return redirect('core:select_clinic')
        
        response = self.get_response(request)
        return response


# class ClinicMiddleware:
#     def __init__(self, get_response):
#         self.get_response = get_response
        
#     def __call__(self, request):
#         clinic_id = request.session.get('clinic_id')
#         if clinic_id:
#             try:
#                 request.clinic = Clinic.objects.get(id=clinic_id)
#             except Clinic.DoesNotExist:
#                 request.clinic = None
#         else:
#             request.clinic = None
            
#         response = self.get_response(request)
#         return response







# class ClinicMiddleware:
#     def __init__(self, get_response):
#         self.get_response = get_response
        
#     def __call__(self, request):
#         if hasattr(request.user, 'primary_clinic'):
#             request.clinic = request.user.primary_clinic
#         else:
#             # Default to general clinic or handle appropriately
#             request.clinic = Clinic.objects.filter(clinic_type='GENERAL').first()
            
#         return self.get_response(request)
