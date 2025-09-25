from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from core.models import Clinic

class Command(BaseCommand):
    help = 'Send subscription reminders and deactivate expired subscriptions'

    def handle(self, *args, **options):
        today = timezone.now().date()
        qs = Clinic.objects.filter(subscription_end_date__isnull=False)

        for clinic in qs:
            days_left = clinic.days_until_expiration()
            if days_left is None:
                continue

            if days_left < 0 and clinic.is_subscription_active:
                clinic.is_subscription_active = False
                clinic.save(update_fields=['is_subscription_active'])
                self._notify_admin(
                    f"Subscription deactivated for {clinic.name}. Expired on {clinic.subscription_end_date}."
                )
                continue

            if days_left == 0 and clinic.last_reminder_sent != 'D0':
                self._send_reminder(clinic, 'D0', "Your subscription expires today")
            elif days_left == 7 and clinic.last_reminder_sent not in ('D7', 'D0'):
                self._send_reminder(clinic, 'D7', "Your subscription will expire in 7 days")
            elif days_left == 14 and clinic.last_reminder_sent not in ('D14', 'D7', 'D0'):
                self._send_reminder(clinic, 'D14', "Your subscription will expire in 14 days")

    def _send_reminder(self, clinic, marker, subject_prefix):
        subject = f"{subject_prefix} - {clinic.name}"
        message = (
            f"Clinic: {clinic.name}\n"
            f"Plan: {clinic.subscription_type}\n"
            f"Expiration Date: {clinic.subscription_end_date}\n\n"
            f"Please renew to avoid interruption."
        )
        try:
            if clinic.email:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [clinic.email], fail_silently=True)
            send_mail(f"ADMIN: {subject}", message, settings.DEFAULT_FROM_EMAIL, ['suavedef@gmail.com'], fail_silently=True)
        except Exception:
            pass
        clinic.last_reminder_sent = marker
        clinic.save(update_fields=['last_reminder_sent'])

    def _notify_admin(self, message):
        try:
            send_mail("Subscription Update", message, settings.DEFAULT_FROM_EMAIL, ['suavedef@gmail.com'], fail_silently=True)
        except Exception:
            pass