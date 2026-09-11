import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import OperationalError

from core.server_sync import (
    internet_available,
    pull_remote_changes,
    push_pending_outbox,
    role,
    sync_worker_lock,
    sync_worker_owner_lock,
)


def is_sqlite_locked_error(exc):
    return 'database is locked' in str(exc).lower()


class Command(BaseCommand):
    help = 'Run the local clinic background sync worker.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Run one sync pass and exit.')
        parser.add_argument('--interval', type=int, default=getattr(settings, 'SYNC_INTERVAL_SECONDS', 30))

    def handle(self, *args, **options):
        if role() != 'local':
            self.stdout.write(self.style.WARNING('sync_worker only runs when SYNC_SERVER_ROLE=local.'))
            return

        with sync_worker_owner_lock() as owns_worker:
            if not owns_worker:
                self.stdout.write(
                    self.style.WARNING(
                        'another managed sync worker already owns this clinic; exiting'
                    )
                )
                return

            self.stdout.write('sync worker ownership acquired')

            while True:
                with sync_worker_lock() as acquired:
                    if not acquired:
                        self.stdout.write('another sync pass is active; waiting')
                    elif internet_available():
                        try:
                            pushed = push_pending_outbox()
                            pull_results = []
                            # Drain several bootstrap/change pages per pass. This keeps a
                            # new clinic from waiting one full interval for every 25 rows.
                            for _ in range(getattr(settings, 'SYNC_PULL_PAGES_PER_PASS', 5)):
                                pulled = pull_remote_changes()
                                pull_results.append(pulled)
                                if not pulled.get('has_more'):
                                    break
                                time.sleep(0.25)
                            self.stdout.write(f"pushed={pushed} pulled={pull_results}")
                        except OperationalError as exc:
                            if not is_sqlite_locked_error(exc):
                                raise
                            self.stderr.write(
                                self.style.WARNING('sync pass skipped because SQLite is busy')
                            )
                            time.sleep(2)
                        except Exception as exc:
                            # A transient network or malformed remote row must not kill
                            # the background worker. The next pass retries safely.
                            self.stderr.write(self.style.ERROR(f'sync pass failed: {exc}'))
                    else:
                        self.stdout.write('central server unavailable; waiting')

                if options['once']:
                    return
                time.sleep(max(5, options['interval']))
