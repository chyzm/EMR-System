import contextlib
import contextvars
import uuid

import requests
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import OperationalError, ProgrammingError
from django.db import transaction
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

    return None


def _json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


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
        if field.is_relation and field.many_to_one:
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
        return model.objects.filter(username=username).first()
    pk_value = value.get(f'{field.name}_id')
    if pk_value:
        return model.objects.filter(pk=pk_value).first()
    return None


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
            if field.is_relation and field.many_to_one:
                related = _find_related(field, payload)
                if related is not None or field.null:
                    setattr(instance, field.name, related)
                continue
            if field.name in payload:
                setattr(instance, field.name, payload[field.name])

        instance.save()

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


def pending_outbox_queryset():
    return ServerSyncOutbox.objects.filter(status__in=['PENDING', 'FAILED']).order_by('created_at')


def push_pending_outbox():
    if role() != 'local':
        return {'processed': 0, 'failed': 0, 'skipped': 'not-local'}
    sync_central_url = central_url()
    sync_token = shared_secret()
    if not sync_central_url or not sync_token:
        return {'processed': 0, 'failed': 0, 'skipped': 'missing-settings'}

    batch_size = getattr(settings, 'SYNC_BATCH_SIZE', 25)
    items = list(pending_outbox_queryset()[:batch_size])
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
    cursor = int(state.value.get('cursor') or 0)
    response = requests.get(
        f'{sync_central_url}/api/server-sync/pull/',
        params={'since': cursor, 'node_id': node_id(), 'clinic_sync_id': local_clinic_sync_id},
        headers={'X-Sync-Token': sync_token},
        timeout=getattr(settings, 'SYNC_REQUEST_TIMEOUT_SECONDS', 20),
    )
    response.raise_for_status()
    data = response.json()
    applied = 0
    for item in data.get('changes', []):
        apply_change(item, origin_node_id=item.get('origin_node_id', 'central'))
        applied += 1
    state.value = {'cursor': data.get('nextCursor', cursor)}
    state.save(update_fields=['value', 'updated_at'])
    return {'applied': applied, 'cursor': state.value['cursor']}


def internet_available():
    sync_central_url = central_url()
    sync_token = shared_secret()
    if not sync_central_url:
        return False
    try:
        response = requests.get(
            f'{sync_central_url}/api/server-sync/health/',
            headers={'X-Sync-Token': sync_token},
            timeout=5,
        )
        return response.status_code == 200
    except requests.RequestException:
        return False
