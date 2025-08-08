from django.core.management.base import BaseCommand
from django.utils import timezone
from DurielMedicApp.models import Patient
from django.core.mail import send_mail

class Command(BaseCommand):
    help = 'Sends birthday notifications and emails'

    def handle(self, *args, **options):
        today = timezone.now().date()
        patients = Patient.objects.filter(
            date_of_birth__month=today.month,
            date_of_birth__day=today.day
        )
        
        for patient in patients:
            # Create notification
            Notification.objects.create(
                user=patient.primary_doctor,  # or whoever should be notified
                message=f"Today is {patient.full_name}'s birthday!",
                link=f"/patients/{patient.id}/"
            )
            
            # Send email if available
            if patient.email:
                send_mail(
                    'Happy Birthday!',
                    f'Dear {patient.full_name},\n\nHappy Birthday from our clinic!',
                    'noreply@yourclinic.com',
                    [patient.email],
                    fail_silently=True
                )