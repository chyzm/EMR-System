from core.models import Clinic
from django.contrib.auth.models import AnonymousUser

class ClinicMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not hasattr(request, 'clinic'):
            clinic_id = request.session.get('clinic_id')
            if clinic_id:
                try:
                    request.clinic = Clinic.objects.get(id=clinic_id)
                except Clinic.DoesNotExist:
                    request.clinic = None
            else:
                request.clinic = None
        
        # Attach user to request for access in signals
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            request.user = AnonymousUser()

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