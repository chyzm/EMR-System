import contextlib
import contextvars
import base64
import binascii
import hashlib
import json
import uuid
from pathlib import Path

import requests
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db import OperationalError, ProgrammingError
from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.db.models.fields.files import FileField
from django.utils import timezone

from core.models import Clinic, ServerSyncChange, ServerSyncOutbox, ServerSyncState


SYNCABLE_MODELS = {
    'core.Clinic',
    'core.Patient',
    'DurielMedicApp.Appointment',
    'DurielMedicApp.Vitals',
    'DurielMedicApp.MedicalRecord',
    'DurielMedicApp.Admission',
    'DurielMedicApp.AdmissionHandover',
    'DurielMedicApp.MedicationAdministration',
    'DurielMedicApp.FollowUp',
    'DurielEyeApp.EyeAppointment',
    'DurielEyeApp.EyeExam',
    'DurielEyeApp.EyeMedicalRecord',
    'DurielEyeApp.EyeFollowUp',
    'DurielDentalApp.DentalAppointment',
    'DurielDentalApp.DentalExam',
    'DurielDentalApp.DentalTreatmentPlan',
    'DurielDentalApp.DentalProcedure',
    'DurielDentalApp.DentalFollowUp',
    'DurielDentalApp.DentalMedicalRecord',
    'core.Billing',
    'core.Payment',
    'core.Prescription',
    'core.ServicePriceList',
    'core.MedicationCategory',
    'core.ClinicMedication',
    'core.StockMovement',
    'core.Notification',
    'core.NotificationRead',
    'core.LabTestCategory',
    'core.LabTest',
    'core.LabTestOrder',
    'core.LabTestResult',
    'DurielMedicApp.PhysiotherapyRecord',
}

_sync_context = contextvars.ContextVar('server_sync_context', default={})


def local_sync_config():
    try:
        state = ServerSyncState.objects.filter(key='local_server').first()
    except (OperationalError, ProgrammingError):
        return {}
    return dict(state.value or {}) if state else {}


def central_url():
    return local_sync_config().get('central_url') or ''


def shared_secret():
    return local_sync_config().get('sync_token') or getattr(settings, 'SYNC_SHARED_SECRET', '')


def clinic_sync_id():
    return local_sync_config().get('clinic_sync_id') or ''


@contextlib.contextmanager
def sync_context(**values):
    current = dict(_sync_context.get())
    current.update(values)
    token = _sync_context.set(current)
    try:
        yield
    finally:
        _sync_context.reset(token)


def should_capture_changes():
    return role() in {'central', 'local'} and not _sync_context.get().get('suppress_capture')


def node_id():
    return local_sync_config().get('node_id') or 'central'


def role():
    config = local_sync_config()
    if config.get('activated'):
        return 'local'
    return getattr(settings, 'SYNC_SERVER_ROLE', 'standalone')


def model_label(model):
    return f'{model._meta.app_label}.{model.__name__}'


def is_syncable_model(model):
    return model_label(model) in SYNCABLE_MODELS


def clinic_for_instance(instance):
    if isinstance(instance, Clinic):
        return instance

    clinic = getattr(instance, 'clinic', None)
    if clinic:
        return clinic

    patient = getattr(instance, 'patient', None)
    if patient:
        return patient.clinic

    appointment = getattr(instance, 'appointment', None)
    if appointment:
        return appointment.clinic

    billing = getattr(instance, 'billing', None)
    if billing:
        return billing.clinic

    notification = getattr(instance, 'notification', None)
    if notification:
        return notification.clinic

    lab_order = getattr(instance, 'lab_test_order', None)
    if lab_order:
        return lab_order.clinic

    medication = getattr(instance, 'medication', None)
    if medication:
        return medication.clinic

    return None


def _json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _serialize_file(value):
    """Return a portable file payload so SQLite and cloud storage stay equivalent."""
    if not value or not getattr(value, 'name', ''):
        return None
    try:
        with value.open('rb') as source:
            content = source.read()
    except (FileNotFoundError, OSError, ValueError):
        return {'name': value.name, 'missing': True}
    return {
        'name': value.name,
        'sha256': hashlib.sha256(content).hexdigest(),
        'content_b64': base64.b64encode(content).decode('ascii'),
    }


def serialize_instance(instance, deleted=False):
    payload = {
        '_model': model_label(instance.__class__),
        '_deleted': deleted,
        '_pk': str(instance.pk),
    }
    if hasattr(instance, 'sync_id'):
        payload['sync_id'] = str(instance.sync_id)

    for field in instance._meta.fields:
        if field.primary_key or field.name == 'id':
            continue
        value = getattr(instance, field.name, None)
        if isinstance(field, FileField):
            payload[field.name] = _serialize_file(value)
            continue
        if field.is_relation and (field.many_to_one or field.one_to_one):
            if value is None:
                payload[f'{field.name}_sync_id'] = None
                payload[f'{field.name}_id'] = None
            elif hasattr(value, 'sync_id'):
                payload[f'{field.name}_sync_id'] = str(value.sync_id)
            elif value.__class__ is get_user_model():
                payload[f'{field.name}_username'] = value.get_username()
            else:
                payload[f'{field.name}_id'] = value.pk
            continue
        payload[field.name] = _json_value(value)
    for field in instance._meta.many_to_many:
        if instance.pk:
            payload[f'{field.name}_refs'] = [
                {'sync_id': str(item.sync_id)} if hasattr(item, 'sync_id') else {'pk': item.pk}
                for item in getattr(instance, field.name).all()
            ]
    generic_related = getattr(instance, 'appointment', None)
    if generic_related is not None and hasattr(generic_related, 'sync_id'):
        payload['_generic_appointment_model'] = model_label(generic_related.__class__)
        payload['_generic_appointment_sync_id'] = str(generic_related.sync_id)
    return payload


def record_change(instance, action, payload=None, operation_id=None, origin_node_id=None):
    if not should_capture_changes() or not is_syncable_model(instance.__class__):
        return None

    clinic = clinic_for_instance(instance)
    if not clinic:
        return None

    origin = origin_node_id or _sync_context.get().get('origin_node_id') or node_id()
    operation_uuid = operation_id or uuid.uuid4()
    record_sync_id = getattr(instance, 'sync_id', None)
    data = payload or serialize_instance(instance, deleted=action == 'delete')

    with transaction.atomic():
        change = ServerSyncChange.objects.create(
            operation_id=operation_uuid,
            clinic=clinic,
            model_label=model_label(instance.__class__),
            action=action,
            record_sync_id=record_sync_id,
            origin_node_id=origin,
            payload=data,
        )
        if role() == 'local':
            ServerSyncOutbox.objects.create(
                operation_id=operation_uuid,
                clinic=clinic,
                model_label=change.model_label,
                action=action,
                record_sync_id=record_sync_id,
                origin_node_id=origin,
                payload=data,
            )
    return change


def _get_model(label):
    app_label, model_name = label.split('.', 1)
    return apps.get_model(app_label, model_name)


def _find_related(field, value):
    model = field.remote_field.model
    sync_value = value.get(f'{field.name}_sync_id')
    if sync_value and hasattr(model, 'sync_id'):
        return model.objects.filter(sync_id=sync_value).first()
    username = value.get(f'{field.name}_username')
    if username and model is get_user_model():
        user = model.objects.filter(username=username).first()
        if user:
            return user
        return model.objects.create(
            username=username,
            email='',
            first_name='Cloud',
            last_name='User',
            role='DOCTOR',
            is_active=False,
            is_staff=False,
            is_superuser=False,
            password=make_password(None),
        )
    pk_value = value.get(f'{field.name}_id')
    if pk_value:
        return model.objects.filter(pk=pk_value).first()
    return None


def _apply_file(instance, field, file_payload):
    current = getattr(instance, field.name)
    if not file_payload:
        if current:
            current.delete(save=False)
        setattr(instance, field.name, '')
        return
    if not isinstance(file_payload, dict):
        # Compatibility with packages that only carried the storage name.
        setattr(instance, field.name, file_payload)
        return
    encoded = file_payload.get('content_b64')
    if not encoded:
        return
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError(f'Invalid file payload for {field.name}')
    expected_hash = file_payload.get('sha256')
    if expected_hash and hashlib.sha256(content).hexdigest() != expected_hash:
        raise ValueError(f'File checksum mismatch for {field.name}')
    name = Path(file_payload.get('name') or field.name).name
    # Storage may rename collisions; the model will retain the returned name.
    current.save(name, ContentFile(content), save=False)


def _apply_generic_appointment(instance, payload):
    label = payload.get('_generic_appointment_model')
    sync_id = payload.get('_generic_appointment_sync_id')
    if not label or not sync_id or not hasattr(instance, 'appointment_content_type'):
        return
    appointment_model = _get_model(label)
    appointment = appointment_model.objects.filter(sync_id=sync_id).first()
    if appointment:
        instance.appointment_content_type = ContentType.objects.get_for_model(appointment)
        instance.appointment_object_id = appointment.pk


def _apply_many_to_many(instance, payload):
    for field in instance._meta.many_to_many:
        refs_key = f'{field.name}_refs'
        if refs_key not in payload:
            continue
        related_ids = []
        related_model = field.remote_field.model
        for reference in payload.get(refs_key) or []:
            if reference.get('sync_id') and hasattr(related_model, 'sync_id'):
                related = related_model.objects.filter(sync_id=reference['sync_id']).first()
            else:
                related = related_model.objects.filter(pk=reference.get('pk')).first()
            if related:
                related_ids.append(related.pk)
        getattr(instance, field.name).set(related_ids)


def apply_change(item, origin_node_id=''):
    label = item['model_label']
    model = _get_model(label)
    payload = item.get('payload') or {}
    action = item.get('action')
    record_sync_id = item.get('record_sync_id') or payload.get('sync_id')

    with sync_context(suppress_capture=True):
        if action == 'delete':
            queryset = model.objects
            if record_sync_id and hasattr(model, 'sync_id'):
                queryset = queryset.filter(sync_id=record_sync_id)
            else:
                queryset = queryset.filter(pk=payload.get('_pk'))
            queryset.delete()
            return

        lookup = {}
        if record_sync_id and hasattr(model, 'sync_id'):
            lookup['sync_id'] = record_sync_id
        elif payload.get('_pk'):
            lookup['pk'] = payload['_pk']
        else:
            raise ValueError(f'Cannot apply {label} without a sync id or pk')

        instance = model.objects.filter(**lookup).first() or model(**lookup)
        for field in model._meta.fields:
            if field.primary_key or field.auto_created:
                continue
            if field.name in {'created_at', 'updated_at'}:
                continue
            if field.is_relation and (field.many_to_one or field.one_to_one):
                related = _find_related(field, payload)
                if related is not None or field.null:
                    setattr(instance, field.name, related)
                continue
            if isinstance(field, FileField) and field.name in payload:
                _apply_file(instance, field, payload[field.name])
                continue
            if field.name in payload:
                setattr(instance, field.name, payload[field.name])

        _apply_generic_appointment(instance, payload)
        instance.save()
        _apply_many_to_many(instance, payload)

    clinic = clinic_for_instance(instance)
    if clinic:
        ServerSyncChange.objects.get_or_create(
            operation_id=item['operation_id'],
            defaults={
                'clinic': clinic,
                'model_label': label,
                'action': action,
                'record_sync_id': record_sync_id,
                'origin_node_id': origin_node_id or item.get('origin_node_id', ''),
                'payload': payload,
            },
        )


def import_remote_users(users, clinic):
    User = get_user_model()
    imported = 0
    for user_payload in users or []:
        if user_payload.get('is_superuser'):
            continue
        username = user_payload.get('username')
        if not username:
            continue
        user, _ = User.objects.update_or_create(
            username=username,
            defaults={
                'email': user_payload.get('email') or '',
                'first_name': user_payload.get('first_name') or '',
                'last_name': user_payload.get('last_name') or '',
                'role': user_payload.get('role') or 'DOCTOR',
                'verified': user_payload.get('verified', False),
                'is_verified': user_payload.get('is_verified', False),
                'is_staff': user_payload.get('is_staff', False),
                'is_superuser': False,
                'is_active': True,
                'password': user_payload.get('password') or make_password(None),
            },
        )
        user.clinic.add(clinic)
        if not user.primary_clinic_id:
            user.primary_clinic = clinic
            user.save(update_fields=['primary_clinic'])
        if 'profile_picture' in user_payload:
            profile_field = User._meta.get_field('profile_picture')
            _apply_file(user, profile_field, user_payload.get('profile_picture'))
            user.save(update_fields=['profile_picture'])
        imported += 1
    return imported


def pending_outbox_queryset():
    max_attempts = getattr(settings, 'SYNC_MAX_RETRY_ATTEMPTS', 10)
    return ServerSyncOutbox.objects.filter(
        Q(status='PENDING') | Q(status='FAILED', attempts__lt=max_attempts)
    ).annotate(
        sync_priority=Case(
            When(status='PENDING', then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by('sync_priority', 'created_at')


def push_pending_outbox():
    if role() != 'local':
        return {'processed': 0, 'failed': 0, 'skipped': 'not-local'}
    sync_central_url = central_url()
    sync_token = shared_secret()
    if not sync_central_url or not sync_token:
        return {'processed': 0, 'failed': 0, 'skipped': 'missing-settings'}

    batch_size = getattr(settings, 'SYNC_BATCH_SIZE', 25)
    candidates = list(pending_outbox_queryset()[:batch_size])
    max_payload_bytes = getattr(settings, 'SYNC_MAX_PAYLOAD_BYTES', 9 * 1024 * 1024)
    items = []
    payload_bytes = 0
    for candidate in candidates:
        item_bytes = len(json.dumps(candidate.payload, separators=(',', ':')).encode('utf-8'))
        if items and payload_bytes + item_bytes > max_payload_bytes:
            break
        items.append(candidate)
        payload_bytes += item_bytes
    if not items:
        return {'processed': 0, 'failed': 0}

    now = timezone.now()
    for item in items:
        item.status = 'SYNCING'
        item.attempts += 1
        item.last_error = ''
    ServerSyncOutbox.objects.bulk_update(items, ['status', 'attempts', 'last_error', 'updated_at'])

    payload = {
        'nodeId': node_id(),
        'items': [
            {
                'operation_id': str(item.operation_id),
                'clinic_sync_id': str(item.clinic.sync_id),
                'model_label': item.model_label,
                'action': item.action,
                'record_sync_id': str(item.record_sync_id) if item.record_sync_id else None,
                'origin_node_id': item.origin_node_id,
                'payload': item.payload,
                'created_at': item.created_at.isoformat(),
            }
            for item in items
        ],
    }

    try:
        response = requests.post(
            f'{sync_central_url}/api/server-sync/push/',
            json=payload,
            headers={'X-Sync-Token': sync_token},
            timeout=getattr(settings, 'SYNC_REQUEST_TIMEOUT_SECONDS', 20),
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        ServerSyncOutbox.objects.filter(id__in=[item.id for item in items]).update(
            status='PENDING',
            last_error=str(exc),
            updated_at=now,
        )
        return {'processed': 0, 'failed': len(items), 'error': str(exc)}

    processed_ids = set(data.get('processed', []))
    failed = {item.get('operation_id'): item.get('error', 'Sync failed') for item in data.get('failed', [])}
    processed_count = 0
    failed_count = 0
    for item in items:
        operation_key = str(item.operation_id)
        if operation_key in processed_ids:
            item.status = 'SYNCED'
            item.last_error = ''
            item.synced_at = now
            processed_count += 1
        else:
            item.status = 'FAILED'
            item.last_error = failed.get(operation_key, 'Central server did not acknowledge this item')
            failed_count += 1
        item.updated_at = now
        item.save(update_fields=['status', 'last_error', 'synced_at', 'updated_at'])
    return {'processed': processed_count, 'failed': failed_count}


def pull_remote_changes():
    if role() != 'local':
        return {'applied': 0, 'skipped': 'not-local'}
    sync_central_url = central_url()
    sync_token = shared_secret()
    if not sync_central_url or not sync_token:
        return {'applied': 0, 'skipped': 'missing-settings'}

    state, _ = ServerSyncState.objects.get_or_create(key='central_pull_cursor', defaults={'value': {'cursor': 0}})
    local_clinic_sync_id = clinic_sync_id()
    if not local_clinic_sync_id:
        return {'applied': 0, 'skipped': 'missing-clinic-sync-id'}
    state_value = dict(state.value or {})
    cursor = int(state_value.get('cursor') or 0)
    required_bootstrap_version = getattr(settings, 'SYNC_BOOTSTRAP_VERSION', 2)
    bootstrap_version_matches = int(state_value.get('bootstrap_version') or 0) == required_bootstrap_version
    bootstrap_done = bool(state_value.get('bootstrap_done')) and bootstrap_version_matches
    bootstrap_offset = int(state_value.get('bootstrap_offset') or 0) if bootstrap_version_matches else 0
    params = {'since': cursor, 'node_id': node_id(), 'clinic_sync_id': local_clinic_sync_id}
    if not bootstrap_done:
        params['bootstrap'] = '1'
        params['bootstrap_offset'] = bootstrap_offset
    response = requests.get(
        f'{sync_central_url}/api/server-sync/pull/',
        params=params,
        headers={'X-Sync-Token': sync_token},
        timeout=getattr(settings, 'SYNC_REQUEST_TIMEOUT_SECONDS', 20),
    )
    response.raise_for_status()
    data = response.json()
    applied = 0
    failures = []
    clinic = Clinic.objects.filter(sync_id=local_clinic_sync_id).first()
    imported_users = import_remote_users(data.get('users') or [], clinic) if clinic else 0
    retry_items = state_value.get('failed_changes') or []
    incoming_items = data.get('changes', [])
    seen_operations = set()
    for item in [*retry_items, *incoming_items]:
        operation_id = str(item.get('operation_id') or '')
        if operation_id in seen_operations:
            continue
        seen_operations.add(operation_id)
        try:
            apply_change(item, origin_node_id=item.get('origin_node_id', 'central'))
            applied += 1
        except Exception as exc:
            failed_item = dict(item)
            failed_item['_last_error'] = str(exc)[:1000]
            failures.append(failed_item)
    remote_bootstrap_done = bool(data.get('bootstrapDone', True))
    state.value = {
        'cursor': data.get('nextCursor', cursor),
        'bootstrap_done': remote_bootstrap_done,
        'bootstrap_offset': 0 if remote_bootstrap_done else data.get('nextBootstrapOffset', bootstrap_offset + applied),
        'failed_changes': failures[-100:],
        'bootstrap_version': required_bootstrap_version if remote_bootstrap_done else state_value.get('bootstrap_version', 0),
    }
    state.save(update_fields=['value', 'updated_at'])
    return {
        'applied': applied,
        'users': imported_users,
        'bootstrap': not bootstrap_done,
        'cursor': state.value['cursor'],
        'failed': len(failures),
    }


def internet_available():
    sync_central_url = central_url()
    sync_token = shared_secret()
    if not sync_central_url:
        return False
    local_clinic_sync_id = clinic_sync_id()
    try:
        response = requests.get(
            f'{sync_central_url}/api/server-sync/health/',
            params={'clinic_sync_id': local_clinic_sync_id} if local_clinic_sync_id else None,
            headers={'X-Sync-Token': sync_token},
            timeout=5,
        )
        return response.status_code == 200
    except requests.RequestException:
        return False
