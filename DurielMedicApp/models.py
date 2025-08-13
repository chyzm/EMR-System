from django.db import models
from django.conf import settings
from core.models import Patient, Clinic

class MedicalRecord(models.Model):
    RECORD_TYPES = (
        ('DIAGNOSIS', 'Diagnosis'),
        ('TREATMENT', 'Treatment Plan'),
        ('PROGRESS', 'Progress Note'),
        ('LAB', 'Lab Result'),
        ('IMAGING', 'Imaging Result'),
        ('PRESCRIPTION', 'Prescription'),
        ('ALLERGY', 'Allergy'),
        ('IMMUNIZATION', 'Immunization'),
        ('PROCEDURE', 'Procedure'),
        ('OTHER', 'Other'),
    )
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='medical_records')
    record_type = models.CharField(max_length=20, choices=RECORD_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.record_type} - {self.title}"


class Appointment(models.Model):
    STATUS_CHOICES = (
        ('SCHEDULED', 'Scheduled'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('NO_SHOW', 'No Show'),
    )
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='appointments')
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='appointments')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='appointments')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='SCHEDULED')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['date', 'start_time']
    
    def __str__(self):
        return f"{self.patient.full_name} with {self.provider.get_full_name()} on {self.date}"


class Vitals(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE)
    blood_pressure = models.CharField(max_length=10)
    pulse = models.IntegerField()
    temperature = models.FloatField()
    weight = models.FloatField()
    notes = models.TextField(blank=True)
    category = models.CharField(choices=[("CONSULT", "Consultation"), ("FOLLOWUP", "Follow-Up")], max_length=20)


class Admission(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    reason = models.TextField()
    date_admitted = models.DateTimeField(auto_now_add=True)
    ward = models.CharField(max_length=50)
    discharged = models.BooleanField(default=False)


class FollowUp(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='follow_ups')
    reason = models.TextField()
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField()
    notes = models.TextField(blank=True, null=True)
    completed = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Follow-up for {self.patient.full_name} on {self.scheduled_date}"


class Prescription(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='prescriptions')
    prescribed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='prescriptions')
    medication = models.CharField(max_length=200)
    dosage = models.CharField(max_length=100)
    frequency = models.CharField(max_length=100)
    duration = models.CharField(max_length=100)
    instructions = models.TextField(blank=True, null=True)
    date_prescribed = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.medication} for {self.patient.full_name}"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.URLField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Notification for {self.user.username if self.user else 'All'} - {self.message[:50]}"


class NotificationRead(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification = models.ForeignKey('Notification', on_delete=models.CASCADE)
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'notification')
