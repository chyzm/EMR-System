import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.server_sync import local_sync_config, role


class Command(BaseCommand):
    help = 'Write the non-secret local updater configuration to a JSON file.'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        output_path = Path(options['output']).expanduser().resolve()
        config = local_sync_config()
        payload = {
            'role': role(),
            'activated': bool(config.get('activated')),
            'clinic_sync_id': config.get('clinic_sync_id') or '',
            'update_manifest_url': config.get('update_manifest_url') or '',
        }
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload), encoding='utf-8')
        except OSError as exc:
            raise CommandError(f'Unable to write updater configuration: {exc}') from exc
