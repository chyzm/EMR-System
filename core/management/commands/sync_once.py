from django.core.management.base import BaseCommand

from core.server_sync import internet_available, pull_remote_changes, push_pending_outbox, role, sync_worker_lock


class Command(BaseCommand):
    help = 'Run one local clinic server sync pass and print the result.'

    def handle(self, *args, **options):
        current_role = role()
        if current_role != 'local':
            self.stdout.write(self.style.WARNING(f'sync_once only runs on an activated local server. role={current_role}'))
            return

        if not internet_available():
            self.stdout.write(self.style.ERROR('Central server unavailable. Check internet, activation URL, and sync token.'))
            return

        with sync_worker_lock() as acquired:
            if not acquired:
                self.stdout.write(
                    self.style.WARNING(
                        'A background sync pass is already active. Try sync_once again shortly.'
                    )
                )
                return

            pushed = push_pending_outbox()
            pulled = pull_remote_changes()
            self.stdout.write(self.style.SUCCESS(f'pushed={pushed} pulled={pulled}'))
