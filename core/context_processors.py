from core.models import Clinic  # adjust import
from core.server_sync import role as server_sync_role

def clinic_context(request):
    clinic_logo_url = None
    clinic_id = request.session.get("clinic_id")
    if clinic_id:
        try:
            clinic = Clinic.objects.get(id=clinic_id)
            if clinic.logo:
                clinic_logo_url = clinic.logo.url
        except Clinic.DoesNotExist:
            pass

    return {
        "clinic_logo_url": clinic_logo_url,
        "server_sync_role": server_sync_role(),
    }
