class ClinicMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        if hasattr(request.user, 'primary_clinic'):
            request.clinic = request.user.primary_clinic
        else:
            # Default to general clinic or handle appropriately
            request.clinic = Clinic.objects.filter(clinic_type='GENERAL').first()
            
        return self.get_response(request)