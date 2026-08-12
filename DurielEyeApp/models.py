from django.db import models
from django.conf import settings
from core.models import Patient, Clinic
import uuid

class EyeMedicalRecord(models.Model):
    RECORD_TYPES = (
        ('DIAGNOSIS', 'Diagnosis'),
        ('TREATMENT', 'Treatment Plan'),
        ('PROGRESS', 'Progress Note'),
        ('IMAGING', 'Imaging Result'),
        ('PRESCRIPTION', 'Prescription'),
        ('PROCEDURE', 'Procedure'),
        ('OTHER', 'Other'),
    )
    
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name='eye_medical_records',
        limit_choices_to={'clinic__clinic_type': 'EYE'}
    )
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name='eye_medical_records',
        limit_choices_to={'clinic_type': 'EYE'}
    )
    record_type = models.CharField(max_length=20, choices=RECORD_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.record_type} - {self.title}"


class EyeAppointment(models.Model):
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
    
    
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name='eye_appointments',
        limit_choices_to={'clinic__clinic_type': 'EYE'}
    )
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='eye_appointments')
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name='eye_appointments',
        limit_choices_to={'clinic_type': 'EYE'}
    )
    
    payment_type = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default='SELF')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='SCHEDULED')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['date', 'start_time']
    
    def __str__(self):
        return f"{self.patient.full_name} with {self.provider.get_full_name()} on {self.date}"


class EyeExam(models.Model):
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='eye_exams')
    appointment = models.ForeignKey(EyeAppointment, on_delete=models.SET_NULL, null=True, blank=True)
    encounter = models.ForeignKey('core.PatientEncounter', on_delete=models.SET_NULL, null=True, blank=True, related_name='eye_exams')

    chief_complaint = models.TextField(blank=True, null=True)
    ocular_history = models.TextField(blank=True, null=True)
    systemic_risk_factors = models.TextField(blank=True, null=True)
    ocular_medications = models.TextField(blank=True, null=True)
    eye_allergies = models.TextField(blank=True, null=True)

    visual_acuity_right = models.CharField(max_length=20, blank=True, null=True)
    visual_acuity_left = models.CharField(max_length=20, blank=True, null=True)
    visual_acuity_right_corrected = models.CharField(max_length=20, blank=True, null=True)
    visual_acuity_left_corrected = models.CharField(max_length=20, blank=True, null=True)
    pinhole_right = models.CharField(max_length=20, blank=True, null=True)
    pinhole_left = models.CharField(max_length=20, blank=True, null=True)
    near_vision_right = models.CharField(max_length=20, blank=True, null=True)
    near_vision_left = models.CharField(max_length=20, blank=True, null=True)

    intraocular_pressure_right = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    intraocular_pressure_left = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

    anterior_segment_findings = models.TextField(blank=True, null=True)
    slit_lamp_findings = models.TextField(blank=True, null=True)
    lens_findings = models.TextField(blank=True, null=True)
    posterior_segment_findings = models.TextField(blank=True, null=True)
    fundus_exam_findings = models.TextField(blank=True, null=True)
    retina_findings = models.TextField(blank=True, null=True)
    optic_disc_findings = models.TextField(blank=True, null=True)

    refraction_right = models.CharField(max_length=50, blank=True, null=True)
    refraction_left = models.CharField(max_length=50, blank=True, null=True)
    objective_refraction_right = models.CharField(max_length=50, blank=True, null=True)
    objective_refraction_left = models.CharField(max_length=50, blank=True, null=True)
    final_prescription_right = models.CharField(max_length=80, blank=True, null=True)
    final_prescription_left = models.CharField(max_length=80, blank=True, null=True)
    pupillary_distance = models.CharField(max_length=30, blank=True, null=True)
    
    sphere_right = models.CharField(max_length=50, default="Not recorded")
    cylinder_right = models.CharField(max_length=50, default="Not recorded")
    axis_right = models.CharField(max_length=50, default="Not recorded")
    add_right = models.CharField(max_length=50, default="Not recorded")
    pupil_size_right = models.CharField(max_length=50, default="Not recorded mm")

    # Left Eye
    sphere_left = models.CharField(max_length=50, default="Not recorded")
    cylinder_left = models.CharField(max_length=50, default="Not recorded")
    axis_left = models.CharField(max_length=50, default="Not recorded")
    add_left = models.CharField(max_length=50, default="Not recorded")
    pupil_size_left = models.CharField(max_length=50, default="Not recorded mm")

    diagnosis = models.TextField(blank=True, null=True)
    treatment_plan = models.TextField(blank=True, null=True)
    procedure_notes = models.TextField(blank=True, null=True)
    imaging_results = models.TextField(blank=True, null=True)
    spectacle_or_contact_lens_plan = models.TextField(blank=True, null=True)
    follow_up_plan = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Eye Exam - {self.patient.full_name} on {self.created_at.strftime('%Y-%m-%d')}"


class EyeFollowUp(models.Model):
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name='eye_follow_ups',
        limit_choices_to={'clinic__clinic_type': 'EYE'}
    )
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name='eye_follow_ups',
        limit_choices_to={'clinic_type': 'EYE'}
    )
    reason = models.TextField()
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField()
    notes = models.TextField(blank=True, null=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Follow-up for {self.patient.full_name} on {self.scheduled_date}"



