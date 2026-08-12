from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from core.models import Notification, Patient

class Command(BaseCommand):
    help = 'Sends birthday notifications and emails'

    def handle(self, *args, **options):
        today = timezone.localdate()
        patients = Patient.objects.filter(
            date_of_birth__month=today.month,
            date_of_birth__day=today.day
        ).select_related('clinic')
        
        notified = 0
        emailed = 0
        for patient in patients:
            if Notification.objects.filter(
                clinic=patient.clinic,
                object_id=str(patient.pk),
                app_name='birthday',
                created_at__date=today,
            ).exists():
                continue

            for user in patient.clinic.staff.filter(is_active=True):
                Notification.objects.create(
                    user=user,
                    clinic=patient.clinic,
                    message=f"Today is {patient.full_name}'s birthday!",
                    link=reverse('core:patient_detail', kwargs={'pk': patient.patient_id}),
                    object_id=str(patient.pk),
                    app_name='birthday',
                )
                notified += 1
            
            if patient.email:
                send_mail(
                    'Happy Birthday!',
                    f'Dear {patient.full_name},\n\nHappy Birthday from {patient.clinic.name}!',
                    settings.DEFAULT_FROM_EMAIL,
                    [patient.email],
                    fail_silently=True
                )
                emailed += 1

        self.stdout.write(self.style.SUCCESS(
            f'Birthday job complete. Notifications: {notified}. Emails attempted: {emailed}.'
        ))
