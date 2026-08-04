import time

from django.conf import settings
from django.core.management.base import BaseCommand

from core.server_sync import internet_available, pull_remote_changes, push_pending_outbox, role


class Command(BaseCommand):
    help = 'Run the local clinic background sync worker.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Run one sync pass and exit.')
        parser.add_argument('--interval', type=int, default=getattr(settings, 'SYNC_INTERVAL_SECONDS', 30))

    def handle(self, *args, **options):
        if role() != 'local':
            self.stdout.write(self.style.WARNING('sync_worker only runs when SYNC_SERVER_ROLE=local.'))
            return

        while True:
            if internet_available():
                pushed = push_pending_outbox()
                pulled = pull_remote_changes()
                self.stdout.write(f"pushed={pushed} pulled={pulled}")
            else:
                self.stdout.write('central server unavailable; waiting')

            if options['once']:
                return
            time.sleep(max(5, options['interval']))
