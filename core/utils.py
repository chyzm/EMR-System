# utils.py
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from .models import ActionLog, Notification, PatientEncounter

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
    ActionLog.objects.create(
        user=user,
        clinic_id=request.session.get('clinic_id'),
        action='LOGOUT',
        details=f"User {user.username} logged out"
    )


def notify_roles(clinic, roles, message, link=None, app_name='', object_id=None, exclude_user=None):
    """Create DB notifications for active users in a clinic with matching roles."""
    if not clinic or not roles:
        return 0

    from django.contrib.auth import get_user_model

    users = get_user_model().objects.filter(
        clinic=clinic,
        role__in=roles,
        is_active=True,
    ).distinct()
    if exclude_user and getattr(exclude_user, 'is_authenticated', False):
        users = users.exclude(pk=exclude_user.pk)

    created = 0
    window_start = timezone.now() - timedelta(minutes=5)
    for user in users:
        exists = Notification.objects.filter(
            user=user,
            clinic=clinic,
            message=message,
            object_id=str(object_id) if object_id is not None else None,
            app_name=app_name or '',
            created_at__gte=window_start,
        ).exists()
        if exists:
            continue
        Notification.objects.create(
            user=user,
            clinic=clinic,
            message=message,
            link=link,
            object_id=str(object_id) if object_id is not None else None,
            app_name=app_name or '',
        )
        created += 1
    return created


def notify_user_db(user, message, link=None, clinic=None, app_name='', object_id=None):
    if not user or not getattr(user, 'is_active', False):
        return None
    return Notification.objects.create(
        user=user,
        clinic=clinic,
        message=message,
        link=link,
        object_id=str(object_id) if object_id is not None else None,
        app_name=app_name or '',
    )


def notify_role_handoff(clinic, roles, message, link=None, app_name='', object_id=None, actor=None, provider=None):
    created = notify_roles(
        clinic,
        roles,
        message,
        link=link,
        app_name=app_name,
        object_id=object_id,
        exclude_user=actor,
    )
    if provider and provider != actor:
        notify_user_db(
            provider,
            message,
            link=link,
            clinic=clinic,
            app_name=app_name,
            object_id=object_id,
        )
        created += 1
    return created


def encounter_type_for_appointment(appointment):
    model_name = appointment.__class__.__name__.lower()
    reason = (getattr(appointment, 'reason', '') or getattr(appointment, 'chief_complaint', '') or '').lower()
    visit_type = (getattr(appointment, 'visit_type', '') or '').lower()
    if 'emergency' in reason or visit_type == 'emergency':
        return 'EMERGENCY'
    if model_name == 'eyeappointment':
        return 'EYE_CONSULTATION'
    if model_name == 'dentalappointment':
        return 'DENTAL_CONSULTATION'
    return 'GENERAL_CONSULTATION'


def get_or_create_encounter_for_appointment(appointment, user=None):
    if not appointment:
        return None
    content_type = ContentType.objects.get_for_model(appointment)
    provider = getattr(appointment, 'provider', None) or getattr(appointment, 'doctor', None)
    encounter, created = PatientEncounter.objects.get_or_create(
        appointment_content_type=content_type,
        appointment_object_id=appointment.pk,
        defaults={
            'patient': appointment.patient,
            'clinic': appointment.clinic,
            'provider': provider,
            'encounter_type': encounter_type_for_appointment(appointment),
            'status': 'OPEN',
            'created_by': user,
        },
    )
    return encounter


def get_or_create_encounter_for_admission(admission, user=None):
    if not admission:
        return None
    encounter_type = 'EMERGENCY' if admission.admission_type == 'EMERGENCY' or admission.admission_source == 'EMERGENCY' else 'ADMISSION'
    encounter, created = PatientEncounter.objects.get_or_create(
        admission=admission,
        defaults={
            'patient': admission.patient,
            'clinic': admission.clinic or admission.patient.clinic,
            'provider': admission.attending_doctor,
            'encounter_type': encounter_type,
            'status': 'DISCHARGED' if admission.discharged else 'IN_PROGRESS',
            'created_by': user or admission.admitted_by,
            'started_at': admission.date_admitted or timezone.now(),
            'ended_at': admission.discharged_at,
        },
    )
    if not admission.encounter_id:
        admission.encounter = encounter
        admission.save(update_fields=['encounter'])
    return encounter


def appointment_billing_filter(appointment):
    if not appointment:
        return {}
    return {
        'appointment_content_type': ContentType.objects.get_for_model(appointment),
        'appointment_object_id': appointment.pk,
    }


def billing_appointment_type(appointment):
    if appointment is None:
        return ''
    model_name = appointment.__class__.__name__.lower()
    if model_name == 'eyeappointment':
        return 'eye'
    if model_name == 'dentalappointment':
        return 'dental'
    return 'general'


def find_service(clinic_id, *terms):
    from .models import ServicePriceList

    queryset = ServicePriceList.objects.filter(clinic_id=clinic_id, is_active=True)
    for term in terms:
        if not term:
            continue
        service = queryset.filter(name__icontains=str(term)).order_by('price', 'name').first()
        if service:
            return service
    return None


def ensure_billing_line_item(*, clinic, patient, appointment=None, encounter=None, source_obj=None,
                             source_type='MANUAL', service=None, description='', quantity=1,
                             unit_price=None, created_by=None, auto_approve=False):
    from .models import BillingLineItem

    if unit_price is None:
        unit_price = getattr(service, 'price', Decimal('0.00')) if service else Decimal('0.00')
    unit_price = Decimal(unit_price or 0)
    quantity = Decimal(quantity or 1)

    appointment_filter = appointment_billing_filter(appointment)
    source_ct = ContentType.objects.get_for_model(source_obj) if source_obj else None
    source_id = str(source_obj.pk) if source_obj else None
    lookup = {
        'clinic': clinic,
        'patient': patient,
        'source_type': source_type,
        'source_content_type': source_ct,
        'source_object_id': source_id,
        **appointment_filter,
    }
    item, created = BillingLineItem.objects.get_or_create(
        **lookup,
        defaults={
            'encounter': encounter,
            'service': service,
            'description': (description or 'Clinical service')[:255],
            'quantity': quantity,
            'unit_price': unit_price,
            'created_by': created_by,
        }
    )
    if not created and item.status in ['DRAFT', 'APPROVED']:
        changed_fields = []
        if encounter and not item.encounter_id:
            item.encounter = encounter
            changed_fields.append('encounter')
        if service and not item.service_id:
            item.service = service
            item.unit_price = unit_price
            changed_fields.extend(['service', 'unit_price', 'total_amount'])
        if changed_fields:
            item.save(update_fields=[*set(changed_fields), 'updated_at'])
    if created and auto_approve:
        item.approve(created_by)
    return item


def ensure_appointment_consultation_charge(appointment, user=None, description=None, source_type='CONSULTATION'):
    if not appointment:
        return None
    encounter = get_or_create_encounter_for_appointment(appointment, user)
    appointment_type = billing_appointment_type(appointment)
    provider_role = getattr(getattr(appointment, 'provider', None), 'role', '')
    label = 'Consultation'
    if provider_role == 'PHYSIOTHERAPIST':
        source_type = 'PHYSIO_CONSULTATION'
        label = 'Physio Consultation'
    elif appointment_type == 'eye':
        label = 'Eye Consultation'
    elif appointment_type == 'dental':
        label = 'Dental Consultation'
    return ensure_billing_line_item(
        clinic=appointment.clinic,
        patient=appointment.patient,
        appointment=appointment,
        encounter=encounter,
        source_obj=appointment,
        source_type=source_type,
        service=None,
        description=description or label,
        unit_price=Decimal('0.00'),
        created_by=user,
        auto_approve=True,
    )


def ensure_admission_charge(admission, user=None):
    if not admission:
        return None
    encounter = get_or_create_encounter_for_admission(admission, user)
    admission_label = admission.get_admission_type_display() if hasattr(admission, 'get_admission_type_display') else 'Admission'
    return ensure_billing_line_item(
        clinic=admission.clinic or admission.patient.clinic,
        patient=admission.patient,
        encounter=encounter,
        source_obj=admission,
        source_type='ADMISSION',
        service=None,
        description=f"{admission_label} admission",
        unit_price=Decimal('0.00'),
        created_by=user,
        auto_approve=True,
    )
