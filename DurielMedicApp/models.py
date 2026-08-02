from django.db import models
from django.conf import settings
from core.models import Patient, Clinic, Prescription

class MedicalRecord(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='medical_records')

    # All sections as separate fields - fill what's relevant
    chief_complaint = models.TextField(blank=True, verbose_name="Chief Complaint")
    history_of_present_illness = models.TextField(blank=True, verbose_name="History of Present Illness")
    past_medical_history = models.TextField(blank=True, verbose_name="Past Medical History")
    diagnosis = models.TextField(blank=True, verbose_name="Diagnosis")
    treatment_plan = models.TextField(blank=True, verbose_name="Treatment Plan")
    lab_results = models.TextField(blank=True, verbose_name="Lab Results")
    imaging_results = models.TextField(blank=True, verbose_name="Imaging Results")
    allergies = models.TextField(blank=True, verbose_name="Allergies")
    procedures = models.TextField(blank=True, verbose_name="Procedures")
    additional_notes = models.TextField(blank=True, verbose_name="Additional Notes")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Medical Record for {self.patient.full_name} - {self.created_at.strftime('%Y-%m-%d')}"


class Appointment(models.Model):
    STATUS_CHOICES = (
        ('SCHEDULED', 'Scheduled'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('NO_SHOW', 'No Show'),
    )
    
    PAYMENT_CHOICES = (
        ('SELF', 'Self Paid'),
        ('INSURANCE', 'Insurance'),
    )
    
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='appointments')
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='appointments')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='appointments')
    payment_type = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default='SELF')
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
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='admissions')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='admissions', null=True, blank=True)
    ward = models.CharField(max_length=50)
    reason = models.TextField()
    admitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admissions_created',
    )
    date_admitted = models.DateTimeField(auto_now_add=True)

    discharged = models.BooleanField(default=False)
    discharged_at = models.DateTimeField(null=True, blank=True)
    discharged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admissions_discharged',
    )

    class Meta:
        ordering = ['-date_admitted']
        indexes = [
            models.Index(fields=['clinic']),
            models.Index(fields=['discharged']),
            models.Index(fields=['-date_admitted']),
        ]

    @property
    def status(self):
        return 'DISCHARGED' if self.discharged else 'ADMITTED'

    def save(self, *args, **kwargs):
        if not self.clinic and self.patient_id:
            self.clinic = self.patient.clinic
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Admission - {self.patient.full_name} ({self.ward})"


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


class PhysiotherapyRecord(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='physiotherapy_records')

    # Physiotherapy-specific fields
    chief_complaint = models.TextField(blank=True, verbose_name="Chief Complaint")
    history_of_present_illness = models.TextField(blank=True, verbose_name="History of Present Illness")
    past_medical_history = models.TextField(blank=True, verbose_name="Past Medical History")
    physical_examination = models.TextField(blank=True, verbose_name="Physical Examination")
    diagnosis = models.TextField(blank=True, verbose_name="Diagnosis")
    treatment_goals = models.TextField(blank=True, verbose_name="Treatment Goals")
    treatment_plan = models.TextField(blank=True, verbose_name="Treatment Plan")
    exercises_prescribed = models.TextField(blank=True, verbose_name="Exercises Prescribed")
    modalities_used = models.TextField(blank=True, verbose_name="Modalities Used")
    progress_notes = models.TextField(blank=True, verbose_name="Progress Notes")
    additional_notes = models.TextField(blank=True, verbose_name="Additional Notes")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Physiotherapy Record for {self.patient.full_name} - {self.created_at.strftime('%Y-%m-%d')}"






