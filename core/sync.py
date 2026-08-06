import json
import uuid
from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.decorators import clinic_selected_required
from core.forms import BillingForm, PatientForm
from core.models import Billing, Clinic, Notification, Patient, Payment, ServerSyncChange, ServicePriceList, SyncOperation
from core.server_sync import apply_change, model_label, role, serialize_instance
from core.utils import log_action
from DurielEyeApp.models import EyeAppointment
from DurielMedicApp.forms import (
    AdmissionForm,
    AppointmentForm,
    FollowUpForm,
    MedicalRecordForm,
    VitalsForm,
)
from DurielMedicApp.models import Admission, Appointment, FollowUp, MedicalRecord, MedicationAdministration, Vitals


INTERNAL_PAYLOAD_FIELDS = {
    'csrfmiddlewaretoken',
    '_sync_id',
    '_patient_sync_id',
    '_appointment_sync_id',
    '_billing_sync_id',
    '_offline_workspace',
}


class SyncValidationError(Exception):
    pass


@require_GET
def service_worker(request):
    script = (settings.BASE_DIR / 'static' / 'sw.js').read_text(encoding='utf-8')
    response = HttpResponse(script, content_type='application/javascript; charset=utf-8')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


def _clean_payload(data):
    return {key: value for key, value in data.items() if key not in INTERNAL_PAYLOAD_FIELDS}


def _form_error(form):
    return form.errors.get_json_data(escape_html=True)


def _operation_uuid(item, clinic):
    raw_value = item.get('operationId') or item.get('operation_id')
    if raw_value:
        try:
            return uuid.UUID(str(raw_value))
        except (TypeError, ValueError, AttributeError):
            raise SyncValidationError('Invalid operation ID')

    legacy_key = item.get('formKey') or json.dumps(item, sort_keys=True, default=str)
    return uuid.uuid5(uuid.NAMESPACE_URL, f'durielmedic:{clinic.sync_id}:{legacy_key}')


def _record_uuid(item, data):
    raw_value = item.get('recordId') or item.get('record_id') or data.get('_sync_id')
    if not raw_value:
        return uuid.uuid4()
    try:
        return uuid.UUID(str(raw_value))
    except (TypeError, ValueError, AttributeError):
        raise SyncValidationError('Invalid record ID')


def _patient_for_payload(data, clinic):
    patient_sync_id = data.get('_patient_sync_id') or data.get('patient_sync_id')
    if patient_sync_id:
        return Patient.objects.get(sync_id=patient_sync_id, clinic=clinic)

    patient_id = data.get('patient_id') or data.get('patient')
    if not patient_id:
        raise SyncValidationError('No patient selected')
    return Patient.objects.get(patient_id=patient_id, clinic=clinic)


def _appointment_for_payload(data, clinic):
    appointment_sync_id = data.get('_appointment_sync_id') or data.get('appointment_sync_id')
    if appointment_sync_id:
        return Appointment.objects.get(sync_id=appointment_sync_id, clinic=clinic)

    appointment_id = data.get('appointment') or data.get('appointment_id')
    if not appointment_id:
        raise SyncValidationError('No appointment selected')
    return Appointment.objects.get(id=appointment_id, clinic=clinic)


def _bill_for_payload(data, clinic, lock=False):
    queryset = Billing.objects.select_for_update() if lock else Billing.objects
    billing_sync_id = data.get('_billing_sync_id') or data.get('billing_sync_id')
    if billing_sync_id:
        return queryset.get(sync_id=billing_sync_id, clinic=clinic)

    bill_id = data.get('bill_id') or data.get('billing_id')
    if not bill_id:
        raise SyncValidationError('No bill referenced')
    return queryset.get(id=bill_id, clinic=clinic)


def _sync_patient(request, item, data):
    form = PatientForm(_clean_payload(data), request=request)
    if not form.is_valid():
        raise SyncValidationError(_form_error(form))
    patient = form.save(commit=False)
    patient.sync_id = _record_uuid(item, data)
    patient.clinic = request.clinic
    patient.created_by = request.user
    patient.save()
    return {
        'recordId': str(patient.sync_id),
        'patient_id': patient.patient_id,
        'server_id': patient.patient_id,
    }


def _sync_appointment(request, item, data):
    form = AppointmentForm(_clean_payload(data))
    form.fields['patient'].queryset = Patient.objects.filter(clinic=request.clinic)
    form.fields['provider'].queryset = get_user_model().objects.filter(
        clinic=request.clinic,
        is_active=True,
    )
    patient = _patient_for_payload(data, request.clinic)
    form.data = form.data.copy()
    form.data['patient'] = patient.patient_id
    if not form.is_valid():
        raise SyncValidationError(_form_error(form))
    appointment = form.save(commit=False)
    appointment.sync_id = _record_uuid(item, data)
    appointment.patient = patient
    appointment.clinic = request.clinic
    appointment.status = 'SCHEDULED'
    appointment.save()
    if patient.status in ['DISCHARGED', 'FOLLOW_UP_COMPLETE']:
        patient.status = 'REGISTERED'
        patient.save(update_fields=['status'])
    staff = get_user_model().objects.filter(clinic=request.clinic, is_active=True).distinct()
    Notification.objects.bulk_create([
        Notification(
            user=user,
            clinic=request.clinic,
            message=f'New appointment with {patient.full_name} on {appointment.date}',
            link=reverse('DurielMedicApp:appointment_list'),
        )
        for user in staff
    ])
    log_action(request, 'CREATE', appointment, details=f'Scheduled appointment for {patient.full_name}')
    return {
        'recordId': str(appointment.sync_id),
        'appointment_id': appointment.id,
        'server_id': appointment.id,
    }


def _sync_vitals(request, item, data):
    appointment = _appointment_for_payload(data, request.clinic)
    form_data = _clean_payload(data)
    form_data['appointment'] = appointment.id
    form = VitalsForm(form_data)
    if not form.is_valid():
        raise SyncValidationError(_form_error(form))
    vitals = form.save(commit=False)
    vitals.sync_id = _record_uuid(item, data)
    vitals.appointment = appointment
    vitals.save()
    patient = appointment.patient
    if patient.status in ['REGISTERED', 'INSURANCE']:
        patient.status = 'VITALS_TAKEN'
        patient.save(update_fields=['status'])
    log_action(request, 'CREATE', vitals, details=f'Recorded vitals for {patient.full_name}')
    return {'recordId': str(vitals.sync_id), 'vitals_id': vitals.id, 'server_id': vitals.id}


def _sync_medical_record(request, item, data):
    patient = _patient_for_payload(data, request.clinic)
    form = MedicalRecordForm(_clean_payload(data))
    if not form.is_valid():
        raise SyncValidationError(_form_error(form))
    record = form.save(commit=False)
    record.sync_id = _record_uuid(item, data)
    record.patient = patient
    record.created_by = request.user
    record.save()
    if data.get('_offline_workspace') and patient.status in ['REGISTERED', 'INSURANCE', 'VITALS_TAKEN', 'IN_CONSULTATION']:
        patient.status = 'CONSULTATION_COMPLETE'
        patient.save(update_fields=['status'])
    log_action(request, 'CREATE', record, details=f'Added medical record for {patient.full_name}')
    return {'recordId': str(record.sync_id), 'record_id': record.id, 'server_id': record.id}


def _sync_admission(request, item, data):
    patient = _patient_for_payload(data, request.clinic)
    if patient.status not in ['VITALS_TAKEN', 'CONSULTATION_COMPLETE']:
        raise SyncValidationError('Patient must have vitals taken or consultation completed first')
    if Admission.objects.filter(patient=patient, clinic=request.clinic, discharged=False).exists():
        raise SyncValidationError('This patient already has an active admission')
    form = AdmissionForm(_clean_payload(data), clinic=request.clinic)
    if not form.is_valid():
        raise SyncValidationError(_form_error(form))
    admission = form.save(commit=False)
    admission.sync_id = _record_uuid(item, data)
    admission.patient = patient
    admission.clinic = request.clinic
    admission.admitted_by = request.user
    if not admission.attending_doctor:
        admission.attending_doctor = request.user
    admission.save()
    appointment = Appointment.objects.filter(
        clinic=request.clinic,
        patient=patient,
        date=timezone.localdate(),
        status='SCHEDULED',
    ).order_by('-start_time').first()
    if appointment:
        appointment.status = 'COMPLETED'
        appointment.save(update_fields=['status'])
    patient.status = 'ADMITTED'
    patient.save(update_fields=['status'])
    log_action(request, 'CREATE', admission, details=f'Admitted patient {patient.full_name} to {admission.ward}')
    return {
        'recordId': str(admission.sync_id),
        'admission_id': admission.id,
        'ward': admission.ward,
        'bed': admission.bed,
        'server_id': admission.id,
    }


def _sync_follow_up(request, item, data):
    patient = _patient_for_payload(data, request.clinic)
    if patient.status not in ['IN_CONSULTATION', 'CONSULTATION_COMPLETE']:
        raise SyncValidationError('Patient must complete consultation first')
    form = FollowUpForm(_clean_payload(data))
    if not form.is_valid():
        raise SyncValidationError(_form_error(form))
    follow_up = form.save(commit=False)
    follow_up.sync_id = _record_uuid(item, data)
    follow_up.patient = patient
    follow_up.created_by = request.user
    follow_up.save()
    patient.status = 'FOLLOW_UP'
    patient.save(update_fields=['status'])
    log_action(request, 'CREATE', follow_up, details=f'Scheduled follow-up for {patient.full_name}')
    return {'recordId': str(follow_up.sync_id), 'follow_up_id': follow_up.id, 'server_id': follow_up.id}


def _sync_bill(request, item, data):
    patient = _patient_for_payload(data, request.clinic)
    form_data = _clean_payload(data)
    form_data['patient'] = patient.patient_id
    form = BillingForm(form_data, clinic_id=request.clinic.id)
    if not form.is_valid():
        raise SyncValidationError(_form_error(form))

    bill = form.save(commit=False)
    bill.sync_id = _record_uuid(item, data)
    bill.created_by = request.user
    bill.clinic = request.clinic
    bill.patient = patient

    appointment_id = data.get('appointment_id')
    appointment_sync_id = data.get('_appointment_sync_id') or data.get('appointment_sync_id')
    appointment_type = data.get('appointment_type', 'general')
    if appointment_sync_id:
        appointment = Appointment.objects.get(sync_id=appointment_sync_id, clinic=request.clinic)
        bill.appointment_object_id = appointment.id
        bill.appointment_content_type = ContentType.objects.get_for_model(appointment)
    elif appointment_id:
        appointment_model = EyeAppointment if appointment_type == 'eye' else Appointment
        appointment = appointment_model.objects.get(id=appointment_id, clinic=request.clinic)
        bill.appointment_object_id = appointment.id
        bill.appointment_content_type = ContentType.objects.get_for_model(appointment)

    services = form.cleaned_data.get('services')
    manual_amount = Decimal(str(form.cleaned_data.get('amount') or 0))
    service_total = sum(service.price for service in services) if services else Decimal('0')
    bill.amount = service_total + manual_amount if services else manual_amount
    bill.paid_amount = bill.paid_amount or 0
    if bill.discount_type != 'NONE' and bill.discount_value > 0:
        bill.discount_applied_by = request.user
        bill.discount_applied_at = timezone.now()
    bill.calculate_final_amount()
    effective_amount = bill.get_effective_amount()
    bill.status = 'PAID' if bill.paid_amount >= effective_amount and effective_amount > 0 else 'PARTIAL' if bill.paid_amount > 0 else 'PENDING'
    bill.save()
    form.save_m2m()
    log_action(request, 'CREATE', bill, details=f'Created bill #{bill.id} for {patient.full_name} - Amount: {bill.amount}')
    return {'recordId': str(bill.sync_id), 'billing_id': bill.id, 'server_id': bill.id}


def _sync_payment(request, item, data):
    bill = _bill_for_payload(data, request.clinic, lock=True)
    raw_amount = data.get('payment_amount') or data.get('amount')
    payment_amount = Decimal(str(raw_amount)) if raw_amount is not None else Decimal('0')
    if payment_amount <= 0:
        raise SyncValidationError('Payment amount must be greater than zero')

    effective_amount = bill.get_effective_amount()
    if payment_amount > effective_amount - bill.paid_amount:
        raise SyncValidationError('Payment amount exceeds outstanding balance')

    bill.paid_amount += payment_amount
    bill.status = 'PAID' if bill.paid_amount >= effective_amount and effective_amount > 0 else 'PARTIAL'
    bill.save()
    payment = Payment.objects.create(
        sync_id=_record_uuid(item, data),
        billing=bill,
        amount=payment_amount,
        received_by=request.user,
        payment_method=data.get('payment_method', 'CASH'),
        transaction_reference=data.get('transaction_reference', ''),
        notes=data.get('notes', ''),
    )
    log_action(request, 'UPDATE', bill, details=f'Recorded payment of ₦{payment_amount:,.2f} for {bill.patient.full_name}')
    return {
        'recordId': str(payment.sync_id),
        'payment_id': payment.id,
        'billing_id': bill.id,
        'payment_amount': str(payment_amount),
        'server_id': payment.id,
    }


ACTION_HANDLERS = {
    'patient_create': _sync_patient,
    'appointment_create': _sync_appointment,
    'record_vitals': _sync_vitals,
    'add_medical_record': _sync_medical_record,
    'admit_patient': _sync_admission,
    'schedule_follow_up': _sync_follow_up,
    'create_bill': _sync_bill,
    'record_payment': _sync_payment,
}

ACTION_ROLES = {
    'patient_create': {'ADMIN', 'DOCTOR', 'RECEPTIONIST', 'NURSE', 'OPTOMETRIST'},
    'appointment_create': {'ADMIN', 'DOCTOR', 'RECEPTIONIST', 'NURSE', 'OPTOMETRIST'},
    'record_vitals': {'ADMIN', 'DOCTOR', 'NURSE'},
    'add_medical_record': {'ADMIN', 'DOCTOR', 'NURSE'},
    'admit_patient': {'ADMIN', 'DOCTOR', 'NURSE'},
    'schedule_follow_up': {'ADMIN', 'DOCTOR'},
    'create_bill': {'ADMIN', 'RECEPTIONIST'},
    'record_payment': {'ADMIN', 'RECEPTIONIST'},
}


def _process_item(request, item, device_id):
    operation_id = _operation_uuid(item, request.clinic)
    form_key = item.get('formKey', str(operation_id))
    existing = SyncOperation.objects.filter(operation_id=operation_id).first()
    if existing:
        if existing.clinic_id != request.clinic.id:
            raise SyncValidationError('Operation belongs to another clinic')
        if existing.status == 'SYNCED':
            return {**existing.result, 'formKey': form_key, 'operationId': str(operation_id), 'duplicate': True}
        if existing.status == 'FAILED':
            raise SyncValidationError(existing.error)

    action = item.get('action')
    handler = ACTION_HANDLERS.get(action)
    if not handler:
        raise SyncValidationError('Unsupported action type')
    if not request.user.is_superuser and request.user.role not in ACTION_ROLES[action]:
        raise SyncValidationError('You do not have permission to synchronize this action')
    data = item.get('payload', {})
    if not isinstance(data, dict):
        raise SyncValidationError('Payload must be an object')

    with transaction.atomic():
        operation = SyncOperation.objects.create(
            operation_id=operation_id,
            clinic=request.clinic,
            user=request.user,
            device_id=device_id,
            action=action,
        )
        result = handler(request, item, data)
        result.update({'formKey': form_key, 'operationId': str(operation_id), 'action': action})
        operation.status = 'SYNCED'
        operation.result = result
        operation.processed_at = timezone.now()
        operation.save(update_fields=['status', 'result', 'processed_at'])
    return result


@login_required
@clinic_selected_required
@require_GET
def offline_bootstrap(request):
    clinic = request.clinic
    offline_expires_at = timezone.now() + timedelta(hours=72)
    recent_cutoff = timezone.localdate() - timedelta(days=30)
    metadata_only = request.GET.get('metadata_only') == '1'
    try:
        patient_page = max(1, int(request.GET.get('patient_page', 1)))
    except (TypeError, ValueError):
        patient_page = 1
    patient_page_size = 250
    patient_offset = (patient_page - 1) * patient_page_size
    patient_batch = [] if metadata_only else list(Patient.objects.filter(clinic=clinic).order_by('-updated_at')[
        patient_offset:patient_offset + patient_page_size + 1
    ])
    has_more_patients = len(patient_batch) > patient_page_size
    patients = patient_batch[:patient_page_size]
    appointments = Appointment.objects.none() if metadata_only else Appointment.objects.filter(
        clinic=clinic,
        date__gte=recent_cutoff,
    ).select_related('patient', 'provider').order_by('date', 'start_time')[:500]
    services = ServicePriceList.objects.none() if metadata_only else ServicePriceList.objects.filter(clinic=clinic, is_active=True).order_by('name')
    bills = Billing.objects.none() if metadata_only else Billing.objects.filter(clinic=clinic).exclude(status__in=['PAID', 'CANCELLED']).select_related('patient').order_by('-updated_at')[:500]
    providers = get_user_model().objects.none() if metadata_only else get_user_model().objects.filter(clinic=clinic, is_active=True).distinct().order_by('first_name', 'last_name')

    return JsonResponse({
        'success': True,
        'csrfToken': get_token(request),
        'generatedAt': timezone.now().isoformat(),
        'offlineExpiresAt': offline_expires_at.isoformat(),
        'patientPage': patient_page,
        'hasMorePatients': has_more_patients,
        'metadataOnly': metadata_only,
        'clinic': {'id': clinic.id, 'sync_id': str(clinic.sync_id), 'name': clinic.name, 'type': clinic.clinic_type},
        'user': {'id': request.user.id, 'username': request.user.username, 'role': request.user.role},
        'patients': [
            {
                'sync_id': str(patient.sync_id),
                'patient_id': patient.patient_id,
                'first_name': patient.first_name,
                'last_name': patient.last_name,
                'date_of_birth': patient.date_of_birth.isoformat(),
                'gender': patient.gender,
                'contact': patient.contact,
                'status': patient.status,
                'updated_at': patient.updated_at.isoformat(),
            }
            for patient in patients
        ],
        'appointments': [
            {
                'sync_id': str(appointment.sync_id),
                'server_id': appointment.id,
                'patient_sync_id': str(appointment.patient.sync_id),
                'provider_id': appointment.provider_id,
                'date': appointment.date.isoformat(),
                'start_time': appointment.start_time.isoformat(),
                'end_time': appointment.end_time.isoformat(),
                'reason': appointment.reason,
                'status': appointment.status,
            }
            for appointment in appointments
        ],
        'services': [
            {'id': service.id, 'name': service.name, 'description': service.description, 'price': str(service.price)}
            for service in services
        ],
        'bills': [
            {
                'sync_id': str(bill.sync_id),
                'server_id': bill.id,
                'patient_sync_id': str(bill.patient.sync_id),
                'amount': str(bill.get_effective_amount()),
                'paid_amount': str(bill.paid_amount),
                'balance': str(bill.get_balance()),
                'description': bill.description,
                'status': bill.status,
                'updated_at': bill.updated_at.isoformat(),
            }
            for bill in bills
        ],
        'providers': [
            {'id': provider.id, 'name': provider.get_full_name() or provider.username, 'role': provider.role}
            for provider in providers
        ],
    })


@login_required
@clinic_selected_required
@require_POST
def sync_queue(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (TypeError, ValueError, UnicodeDecodeError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON payload'}, status=400)

    queue_items = payload.get('items', [])
    if not isinstance(queue_items, list):
        return JsonResponse({'success': False, 'error': 'items must be a list'}, status=400)
    if len(queue_items) > 25:
        return JsonResponse({'success': False, 'error': 'A sync batch may contain at most 25 items'}, status=400)

    device_id = str(payload.get('deviceId', 'legacy-device'))[:64]
    processed = []
    failed = []
    for item in queue_items:
        form_key = item.get('formKey', '') if isinstance(item, dict) else ''
        try:
            if not isinstance(item, dict):
                raise SyncValidationError('Queue item must be an object')
            processed.append(_process_item(request, item, device_id))
        except Exception as exc:
            failed.append({
                'formKey': form_key,
                'operationId': item.get('operationId', '') if isinstance(item, dict) else '',
                'error': str(exc),
            })

    return JsonResponse({'success': True, 'processed': processed, 'failed': failed})


def _server_sync_authorized(request):
    expected = getattr(settings, 'SYNC_SHARED_SECRET', '')
    supplied = request.headers.get('X-Sync-Token')
    if expected and supplied == expected:
        return True

    clinic_sync_id = request.GET.get('clinic_sync_id')
    if request.method == 'POST' and not clinic_sync_id:
        try:
            payload = json.loads(request.body.decode('utf-8'))
            first_item = (payload.get('items') or [{}])[0]
            clinic_sync_id = first_item.get('clinic_sync_id') or (first_item.get('payload') or {}).get('clinic_sync_id')
        except Exception:
            clinic_sync_id = None

    if supplied and clinic_sync_id:
        try:
            value = signing.loads(supplied, salt='clinic-local-server-sync')
        except signing.BadSignature:
            return False
        return value.get('clinic_sync_id') == str(clinic_sync_id)

    return False


def _activation_authorized(request):
    expected = getattr(settings, 'SYNC_ACTIVATION_TOKEN', '') or getattr(settings, 'SYNC_SHARED_SECRET', '')
    supplied = request.GET.get('token') or request.headers.get('X-Sync-Activation-Token')
    if expected and supplied == expected:
        return True

    signed_token = request.GET.get('activation')
    clinic_sync_id = request.GET.get('clinic_sync_id')
    if signed_token and clinic_sync_id:
        try:
            value = signing.loads(signed_token, salt='clinic-local-server-activation', max_age=7 * 24 * 60 * 60)
        except signing.BadSignature:
            return False
        return value.get('clinic_sync_id') == clinic_sync_id

    return False


def _server_sync_endpoint_is_central():
    return role() != 'local'


def _clinic_sync_token(clinic):
    return getattr(settings, 'SYNC_SHARED_SECRET', '') or signing.dumps(
        {'clinic_sync_id': str(clinic.sync_id)},
        salt='clinic-local-server-sync',
    )


SERVER_SYNC_SNAPSHOT_MODELS = (
    'core.Clinic',
    'core.Patient',
    'core.ServicePriceList',
    'core.MedicationCategory',
    'core.ClinicMedication',
    'DurielMedicApp.Appointment',
    'DurielEyeApp.EyeAppointment',
    'DurielDentalApp.DentalAppointment',
    'DurielMedicApp.Vitals',
    'DurielMedicApp.MedicalRecord',
    'DurielEyeApp.EyeMedicalRecord',
    'DurielEyeApp.EyeExam',
    'DurielDentalApp.DentalExam',
    'DurielMedicApp.Admission',
    'core.Prescription',
    'core.Billing',
    'core.StockMovement',
    'DurielMedicApp.MedicationAdministration',
    'DurielMedicApp.AdmissionHandover',
    'DurielMedicApp.FollowUp',
    'DurielEyeApp.EyeFollowUp',
    'DurielDentalApp.DentalTreatmentPlan',
    'DurielDentalApp.DentalProcedure',
    'DurielDentalApp.DentalFollowUp',
    'DurielDentalApp.DentalMedicalRecord',
    'core.Payment',
    'core.Notification',
    'core.NotificationRead',
    'core.LabTestCategory',
    'core.LabTest',
    'core.LabTestOrder',
    'core.LabTestResult',
    'DurielMedicApp.PhysiotherapyRecord',
)


def _snapshot_queryset_for_clinic(model, clinic):
    label = model_label(model)
    if label == 'core.Clinic':
        return model.objects.filter(pk=clinic.pk)
    if label == 'DurielMedicApp.Vitals':
        return model.objects.filter(appointment__clinic=clinic)
    if label == 'core.Payment':
        return model.objects.filter(billing__clinic=clinic)
    if label == 'core.NotificationRead':
        return model.objects.filter(notification__clinic=clinic)
    if label == 'core.LabTestResult':
        return model.objects.filter(lab_test_order__clinic=clinic)
    if label == 'core.StockMovement':
        return model.objects.filter(medication__clinic=clinic)
    if label in {'DurielMedicApp.AdmissionHandover', 'DurielMedicApp.MedicationAdministration'}:
        return model.objects.filter(patient__clinic=clinic)
    if hasattr(model, 'clinic'):
        return model.objects.filter(clinic=clinic)
    if hasattr(model, 'patient'):
        return model.objects.filter(patient__clinic=clinic)
    return model.objects.none()


def _snapshot_change(instance, clinic):
    label = model_label(instance.__class__)
    record_sync_id = getattr(instance, 'sync_id', None)
    operation_id = uuid.uuid5(uuid.NAMESPACE_URL, f'durielmedic-bootstrap:{clinic.sync_id}:{label}:{record_sync_id or instance.pk}')
    return {
        'id': 0,
        'operation_id': str(operation_id),
        'clinic_sync_id': str(clinic.sync_id),
        'model_label': label,
        'action': 'update',
        'record_sync_id': str(record_sync_id) if record_sync_id else None,
        'origin_node_id': 'central-bootstrap',
        'payload': serialize_instance(instance),
        'created_at': timezone.now().isoformat(),
    }


def _clinic_snapshot_changes(clinic, offset=0, limit=25):
    changes = []
    skipped = 0
    payload_bytes = 0
    max_payload_bytes = getattr(settings, 'SYNC_MAX_PAYLOAD_BYTES', 9 * 1024 * 1024)
    for label in SERVER_SYNC_SNAPSHOT_MODELS:
        app_label, model_name = label.split('.', 1)
        model = apps.get_model(app_label, model_name)
        for instance in _snapshot_queryset_for_clinic(model, clinic).iterator():
            if skipped < offset:
                skipped += 1
                continue
            change = _snapshot_change(instance, clinic)
            change_bytes = len(json.dumps(change, separators=(',', ':')).encode('utf-8'))
            if changes and payload_bytes + change_bytes > max_payload_bytes:
                return changes, True
            changes.append(change)
            payload_bytes += change_bytes
            if len(changes) > limit:
                return changes[:limit], True
    return changes, False


@require_GET
def server_sync_health(request):
    if not _server_sync_authorized(request):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    return JsonResponse({'success': True, 'role': getattr(settings, 'SYNC_SERVER_ROLE', 'standalone')})


@require_GET
def server_sync_activate(request):
    if not _activation_authorized(request):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    if not _server_sync_endpoint_is_central():
        return JsonResponse({'success': False, 'error': 'Activation is only available on the central server'}, status=400)

    clinic_sync_id = request.GET.get('clinic_sync_id')
    if not clinic_sync_id:
        return JsonResponse({'success': False, 'error': 'clinic_sync_id is required'}, status=400)
    try:
        clinic = Clinic.objects.get(sync_id=clinic_sync_id)
    except Clinic.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Unknown clinic'}, status=404)

    users = []
    for user in get_user_model().objects.filter(
        Q(clinic=clinic) | Q(primary_clinic=clinic),
        is_active=True,
        is_superuser=False,
    ).distinct():
        users.append({
            'username': user.get_username(),
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': getattr(user, 'role', 'DOCTOR'),
            'verified': getattr(user, 'verified', False),
            'is_verified': getattr(user, 'is_verified', False),
            'is_staff': user.is_staff,
            'password': user.password,
            'profile_picture': serialize_instance(user).get('profile_picture'),
        })

    central_url = request.build_absolute_uri('/').rstrip('/')
    return JsonResponse({
        'success': True,
        'central_url': central_url,
        'update_manifest_url': getattr(settings, 'SYNC_UPDATE_MANIFEST_URL', ''),
        'sync_token': _clinic_sync_token(clinic),
        'clinic': {
            'sync_id': str(clinic.sync_id),
            'name': clinic.name,
            'clinic_type': clinic.clinic_type,
            'address': clinic.address,
            'phone': clinic.phone,
            'email': clinic.email,
            'website': clinic.website,
            'subscription_type': clinic.subscription_type,
            'subscription_start_date': clinic.subscription_start_date.isoformat() if clinic.subscription_start_date else None,
            'subscription_end_date': clinic.subscription_end_date.isoformat() if clinic.subscription_end_date else None,
            'is_subscription_active': clinic.is_subscription_active,
            'last_reminder_sent': clinic.last_reminder_sent,
        },
        'users': users,
    })


@csrf_exempt
@require_POST
def server_sync_push(request):
    if not _server_sync_authorized(request):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    if not _server_sync_endpoint_is_central():
        return JsonResponse({'success': False, 'error': 'This endpoint is only enabled on the central server'}, status=400)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (TypeError, ValueError, UnicodeDecodeError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON payload'}, status=400)

    node_id = str(payload.get('nodeId') or '')
    items = payload.get('items', [])
    if not isinstance(items, list):
        return JsonResponse({'success': False, 'error': 'items must be a list'}, status=400)
    if len(items) > getattr(settings, 'SYNC_BATCH_SIZE', 25):
        return JsonResponse({'success': False, 'error': 'Batch is too large'}, status=400)

    processed = []
    failed = []
    for item in items:
        operation_id = str(item.get('operation_id') or '')
        try:
            operation_uuid = uuid.UUID(operation_id)
            clinic_sync_id = item.get('clinic_sync_id') or (item.get('payload') or {}).get('clinic_sync_id')
            if not clinic_sync_id:
                raise SyncValidationError('No clinic sync id supplied')
            Clinic.objects.get(sync_id=clinic_sync_id)
            if ServerSyncChange.objects.filter(operation_id=operation_uuid).exists():
                processed.append(operation_id)
                continue
            item['operation_id'] = operation_id
            item['origin_node_id'] = item.get('origin_node_id') or node_id
            apply_change(item, origin_node_id=item['origin_node_id'])
            processed.append(operation_id)
        except Exception as exc:
            failed.append({'operation_id': operation_id, 'error': str(exc)})

    return JsonResponse({'success': True, 'processed': processed, 'failed': failed})


@require_GET
def server_sync_pull(request):
    if not _server_sync_authorized(request):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    if not _server_sync_endpoint_is_central():
        return JsonResponse({'success': False, 'error': 'This endpoint is only enabled on the central server'}, status=400)

    try:
        since = max(0, int(request.GET.get('since', 0)))
    except (TypeError, ValueError):
        since = 0
    requester_node_id = request.GET.get('node_id', '')
    clinic_sync_id = request.GET.get('clinic_sync_id')
    include_bootstrap = request.GET.get('bootstrap') in {'1', 'true', 'yes'}
    try:
        bootstrap_offset = max(0, int(request.GET.get('bootstrap_offset', 0)))
    except (TypeError, ValueError):
        bootstrap_offset = 0
    if not clinic_sync_id:
        return JsonResponse({'success': False, 'error': 'clinic_sync_id is required'}, status=400)
    try:
        clinic = Clinic.objects.get(sync_id=clinic_sync_id)
    except Clinic.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Unknown clinic'}, status=404)

    batch_size = getattr(settings, 'SYNC_BATCH_SIZE', 25)
    bootstrap_done = True
    has_more = False
    if include_bootstrap:
        changes, has_more_bootstrap = _clinic_snapshot_changes(clinic, bootstrap_offset, batch_size)
        bootstrap_done = not has_more_bootstrap
        has_more = has_more_bootstrap
        change_items = []
    else:
        changes = []
        queryset = ServerSyncChange.objects.filter(clinic=clinic, id__gt=since)
        if requester_node_id:
            queryset = queryset.exclude(origin_node_id=requester_node_id)
        change_items = list(queryset.order_by('id')[:batch_size + 1])
        has_more = len(change_items) > batch_size
        change_items = change_items[:batch_size]

    changes.extend([
        {
            'id': item.id,
            'operation_id': str(item.operation_id),
            'clinic_sync_id': str(item.clinic.sync_id),
            'model_label': item.model_label,
            'action': item.action,
            'record_sync_id': str(item.record_sync_id) if item.record_sync_id else None,
            'origin_node_id': item.origin_node_id,
            'payload': item.payload,
            'created_at': item.created_at.isoformat(),
        }
        for item in change_items
    ])
    users = []
    for user in get_user_model().objects.filter(
        Q(clinic=clinic) | Q(primary_clinic=clinic),
        is_active=True,
        is_superuser=False,
    ).distinct():
        users.append({
            'username': user.get_username(),
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': getattr(user, 'role', 'DOCTOR'),
            'verified': getattr(user, 'verified', False),
            'is_verified': getattr(user, 'is_verified', False),
            'is_staff': user.is_staff,
            'password': user.password,
            'profile_picture': serialize_instance(user).get('profile_picture'),
        })

    real_change_ids = [item['id'] for item in changes if item.get('id', 0) > 0]
    next_cursor = real_change_ids[-1] if real_change_ids else since
    return JsonResponse({
        'success': True,
        'changes': changes,
        'users': users,
        'nextCursor': next_cursor,
        'bootstrapDone': bootstrap_done,
        'nextBootstrapOffset': bootstrap_offset + len(changes) if include_bootstrap else 0,
        'hasMore': has_more,
    })
