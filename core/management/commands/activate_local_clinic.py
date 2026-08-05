import uuid
from datetime import date

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Clinic, ServerSyncState
from core.server_sync import import_remote_users, sync_context


def parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


class Command(BaseCommand):
    help = 'Activate a local clinic server from a cloud activation URL.'

    def add_arguments(self, parser):
        parser.add_argument('activation_url', help='Cloud activation URL copied from the clinic cloud account.')
        parser.add_argument('--timeout', type=int, default=30)

    def handle(self, *args, **options):
        activation_url = options['activation_url']
        try:
            response = requests.get(activation_url, timeout=options['timeout'])
            if response.status_code >= 400:
                raise CommandError(
                    f'Activation request failed with HTTP {response.status_code}: {response.text[:1000]}'
                )
            payload = response.json()
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f'Unable to activate local clinic server: {exc}') from exc

        if not payload.get('success'):
            raise CommandError(payload.get('error') or 'Activation failed.')

        clinic_payload = payload.get('clinic') or {}
        clinic_sync_id = clinic_payload.get('sync_id')
        if not clinic_sync_id:
            raise CommandError('Activation payload did not include a clinic sync id.')

        node_id = payload.get('node_id') or str(uuid.uuid4())
        central_url = (payload.get('central_url') or '').rstrip('/')
        update_manifest_url = payload.get('update_manifest_url') or ''
        sync_token = payload.get('sync_token') or ''
        if not central_url or not sync_token:
            raise CommandError('Activation payload did not include central_url and sync_token.')

        with transaction.atomic(), sync_context(suppress_capture=True):
            clinic, _ = Clinic.objects.update_or_create(
                sync_id=clinic_sync_id,
                defaults={
                    'name': clinic_payload.get('name') or 'Clinic',
                    'clinic_type': clinic_payload.get('clinic_type') or 'GENERAL',
                    'address': clinic_payload.get('address') or '',
                    'phone': clinic_payload.get('phone') or '',
                    'email': clinic_payload.get('email') or '',
                    'website': clinic_payload.get('website') or '',
                    'subscription_type': clinic_payload.get('subscription_type') or None,
                    'subscription_start_date': parse_date(clinic_payload.get('subscription_start_date')),
                    'subscription_end_date': parse_date(clinic_payload.get('subscription_end_date')),
                    'is_subscription_active': bool(clinic_payload.get('is_subscription_active', False)),
                    'last_reminder_sent': clinic_payload.get('last_reminder_sent') or 'NONE',
                },
            )
            imported_users = import_remote_users(payload.get('users') or [], clinic)
            ServerSyncState.objects.update_or_create(
                key='local_server',
                defaults={
                    'value': {
                        'activated': True,
                        'central_url': central_url,
                        'update_manifest_url': update_manifest_url,
                        'clinic_sync_id': str(clinic.sync_id),
                        'node_id': node_id,
                        'sync_token': sync_token,
                    },
                },
            )

        self.stdout.write(self.style.SUCCESS('Local clinic server activated.'))
        self.stdout.write(f'Clinic: {clinic.name} ({clinic.sync_id})')
        self.stdout.write(f'Node ID: {node_id}')
        self.stdout.write(f'Users imported/updated: {imported_users}')
