import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import Clinic, Patient


class DentalAppointment(models.Model):
    STATUS_CHOICES = (
        ('SCHEDULED', 'Scheduled'),
        ('CHECKED_IN', 'Checked In'),
        ('IN_CHAIR', 'In Chair'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('NO_SHOW', 'No Show'),
    )
    VISIT_TYPES = (
        ('CONSULTATION', 'Consultation'),
        ('CHECKUP', 'Routine Checkup'),
        ('CLEANING', 'Scaling/Cleaning'),
        ('RESTORATION', 'Restoration/Filling'),
        ('EXTRACTION', 'Extraction'),
        ('ROOT_CANAL', 'Root Canal'),
        ('ORTHODONTICS', 'Orthodontics'),
        ('SURGERY', 'Oral Surgery'),
        ('EMERGENCY', 'Emergency'),
    )
    PAYMENT_CHOICES = (
        ('SELF', 'Self Paid'),
        ('INSURANCE', 'Insurance'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='dental_appointments', limit_choices_to={'clinic__clinic_type': 'DENTAL'})
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='dental_appointments')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='dental_appointments', limit_choices_to={'clinic_type': 'DENTAL'})
    visit_type = models.CharField(max_length=20, choices=VISIT_TYPES, default='CONSULTATION')
    payment_type = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default='SELF')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    chief_complaint = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='SCHEDULED')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_dental_appointments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['clinic', 'date', 'status'], name='DurielDenta_clinic__38b4d8_idx'),
            models.Index(fields=['provider', 'date'], name='DurielDenta_provide_22c781_idx'),
        ]

    def __str__(self):
        return f"{self.patient.full_name} - {self.get_visit_type_display()} on {self.date}"


class DentalExam(models.Model):
    OCCLUSION_CHOICES = (
        ('NORMAL', 'Normal'),
        ('CLASS_I', 'Class I'),
        ('CLASS_II', 'Class II'),
        ('CLASS_III', 'Class III'),
        ('OPEN_BITE', 'Open Bite'),
        ('CROSS_BITE', 'Cross Bite'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='dental_exams', limit_choices_to={'clinic__clinic_type': 'DENTAL'})
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='dental_exams', limit_choices_to={'clinic_type': 'DENTAL'})
    appointment = models.ForeignKey(DentalAppointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='exams')
    chief_complaint = models.TextField(blank=True)
    medical_alerts = models.TextField(blank=True)
    extraoral_exam = models.TextField(blank=True)
    intraoral_exam = models.TextField(blank=True)
    periodontal_findings = models.TextField(blank=True)
    occlusion = models.CharField(max_length=20, choices=OCCLUSION_CHOICES, blank=True)
    diagnosis = models.TextField(blank=True)
    treatment_recommendation = models.TextField(blank=True)
    tooth_chart = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['patient', '-created_at'], name='DurielDenta_patient_960a02_idx'),
            models.Index(fields=['clinic', '-created_at'], name='DurielDenta_clinic__94af23_idx'),
        ]

    def __str__(self):
        return f"Dental exam - {self.patient.full_name} ({self.created_at:%Y-%m-%d})"


class DentalTreatmentPlan(models.Model):
    STATUS_CHOICES = (
        ('PROPOSED', 'Proposed'),
        ('ACCEPTED', 'Accepted'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('DECLINED', 'Declined'),
    )
    PRIORITY_CHOICES = (
        ('LOW', 'Low'),
        ('ROUTINE', 'Routine'),
        ('URGENT', 'Urgent'),
        ('EMERGENCY', 'Emergency'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='dental_treatment_plans')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='dental_treatment_plans')
    exam = models.ForeignKey(DentalExam, on_delete=models.SET_NULL, null=True, blank=True, related_name='treatment_plans')
    title = models.CharField(max_length=200)
    diagnosis = models.TextField(blank=True)
    proposed_treatment = models.TextField()
    priority = models.CharField(max_length=12, choices=PRIORITY_CHOICES, default='ROUTINE')
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='PROPOSED')
    consent_obtained = models.BooleanField(default=False)
    consent_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.patient.full_name}"


class DentalProcedure(models.Model):
    STATUS_CHOICES = (
        ('PLANNED', 'Planned'),
        ('DONE', 'Done'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='dental_procedures')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='dental_procedures')
    appointment = models.ForeignKey(DentalAppointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='procedures')
    treatment_plan = models.ForeignKey(DentalTreatmentPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='procedures')
    tooth_numbers = models.CharField(max_length=100, blank=True, help_text='FDI/Universal notation, e.g. 11, 12, 36')
    procedure_name = models.CharField(max_length=200)
    materials_used = models.TextField(blank=True)
    anesthesia = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DONE')
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    performed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-performed_at']
        indexes = [
            models.Index(fields=['patient', '-performed_at'], name='DurielDenta_patient_c19f21_idx'),
            models.Index(fields=['clinic', '-performed_at'], name='DurielDenta_clinic__9d1540_idx'),
        ]

    def __str__(self):
        return f"{self.procedure_name} - {self.patient.full_name}"


class DentalFollowUp(models.Model):
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='dental_follow_ups')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='dental_follow_ups')
    treatment_plan = models.ForeignKey(DentalTreatmentPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='follow_ups')
    reason = models.TextField()
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField()
    notes = models.TextField(blank=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_date', 'scheduled_time']

    def __str__(self):
        return f"Dental follow-up for {self.patient.full_name} on {self.scheduled_date}"


class DentalMedicalRecord(models.Model):
    RECORD_TYPES = (
        ('DIAGNOSIS', 'Diagnosis'),
        ('TREATMENT_NOTE', 'Treatment Note'),
        ('IMAGING', 'Imaging/X-ray'),
        ('PRESCRIPTION', 'Prescription'),
        ('CONSENT', 'Consent'),
        ('OTHER', 'Other'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='dental_medical_records')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='dental_medical_records')
    record_type = models.CharField(max_length=20, choices=RECORD_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_record_type_display()} - {self.patient.full_name}"
