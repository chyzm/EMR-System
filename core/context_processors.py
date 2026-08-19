from core.models import Clinic  # adjust import
from core.permissions import (
    can_manage_patient_demographics,
    can_prescribe,
    can_view_patient,
    has_role,
    is_admin_user,
)
from core.server_sync import role as server_sync_role


def permission_context(request):
    user = getattr(request, "user", None)
    clinic_type = request.session.get("clinic_type")

    is_general = clinic_type == "GENERAL"
    is_eye = clinic_type == "EYE"
    is_dental = clinic_type == "DENTAL"

    can_access_administration = is_admin_user(user)
    can_access_activity_log = has_role(user, "ADMIN")
    can_access_patients = can_view_patient(user)
    can_create_patient = can_manage_patient_demographics(user)
    can_delete_patient = can_access_administration
    can_view_billing_status = has_role(user, "ADMIN", "RECEPTIONIST")
    can_manage_billing = has_role(user, "ADMIN", "RECEPTIONIST")
    can_manage_services = has_role(user, "ADMIN", "RECEPTIONIST")
    can_access_pharmacy = has_role(user, "ADMIN", "PHARMACIST")
    can_access_lab_queue = has_role(user, "DOCTOR", "NURSE", "LAB_TECHNICIAN")
    can_manage_lab = has_role(user, "ADMIN")
    can_view_reports = has_role(user, "ADMIN")
    can_access_settings = has_role(user, "ADMIN")
    can_access_admissions = has_role(user, "ADMIN", "DOCTOR", "NURSE") and is_general
    can_access_vitals = has_role(user, "ADMIN", "RECEPTIONIST", "NURSE", "DOCTOR", "OPTOMETRIST", "DENTIST")
    can_access_eye_consultation = is_eye and has_role(user, "DOCTOR", "OPTOMETRIST")
    can_access_optical_lab = is_eye and has_role(user, "OPTICIAN")
    can_manage_eye_appointments = is_eye and has_role(
        user,
        "ADMIN",
        "DOCTOR",
        "OPTOMETRIST",
        "OPTICIAN",
        "RECEPTIONIST",
        "NURSE",
    )
    can_delete_eye_appointments = is_eye and has_role(user, "ADMIN", "RECEPTIONIST", "NURSE")
    can_manage_eye_followups = is_eye and has_role(
        user,
        "ADMIN",
        "DOCTOR",
        "OPTOMETRIST",
        "RECEPTIONIST",
        "NURSE",
    )
    can_complete_eye_followups = is_eye and has_role(user, "DOCTOR", "OPTOMETRIST", "NURSE")
    can_access_appointments = has_role(
        user,
        "ADMIN",
        "DOCTOR",
        "DENTIST",
        "RECEPTIONIST",
        "NURSE",
        "OPTOMETRIST",
    )
    can_create_appointment = (
        (is_general and has_role(user, "ADMIN", "RECEPTIONIST", "NURSE", "DOCTOR"))
        or (is_eye and has_role(user, "ADMIN", "RECEPTIONIST", "NURSE"))
        or (is_dental and has_role(user, "ADMIN", "RECEPTIONIST", "NURSE"))
    )
    can_view_followups = has_role(
        user,
        "ADMIN",
        "DOCTOR",
        "DENTIST",
        "NURSE",
        "RECEPTIONIST",
        "OPTOMETRIST",
    )
    can_view_dental_chart = is_dental and has_role(user, "DENTIST")
    can_access_dental_procedures = can_view_dental_chart
    can_see_appointment_badge = (
        (is_general and has_role(user, "DOCTOR"))
        or (is_eye and has_role(user, "DOCTOR", "OPTOMETRIST"))
        or (is_dental and has_role(user, "DENTIST"))
    )

    return {
        "can_access_administration": can_access_administration,
        "can_access_activity_log": can_access_activity_log,
        "can_access_patients": can_access_patients,
        "can_create_patient": can_create_patient,
        "can_delete_patient": can_delete_patient,
        "can_view_billing_status": can_view_billing_status,
        "can_access_appointments": can_access_appointments,
        "can_create_appointment": can_create_appointment,
        "can_view_followups": can_view_followups,
        "can_access_pharmacy": can_access_pharmacy,
        "can_manage_services": can_manage_services,
        "can_manage_billing": can_manage_billing,
        "can_access_lab_queue": can_access_lab_queue,
        "can_manage_lab": can_manage_lab,
        "can_view_reports": can_view_reports,
        "can_access_settings": can_access_settings,
        "can_access_admissions": can_access_admissions,
        "can_access_vitals": can_access_vitals,
        "can_access_eye_consultation": can_access_eye_consultation,
        "can_access_optical_lab": can_access_optical_lab,
        "can_manage_eye_appointments": can_manage_eye_appointments,
        "can_delete_eye_appointments": can_delete_eye_appointments,
        "can_manage_eye_followups": can_manage_eye_followups,
        "can_complete_eye_followups": can_complete_eye_followups,
        "can_prescribe": can_prescribe(user),
        "can_view_dental_chart": can_view_dental_chart,
        "can_access_dental_procedures": can_access_dental_procedures,
        "can_see_appointment_badge": can_see_appointment_badge,
    }

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
        **permission_context(request),
    }
