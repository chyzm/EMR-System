from django.db import models
from django.conf import settings
from core.models import Patient, Clinic

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
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='eye_exams')
    appointment = models.ForeignKey(EyeAppointment, on_delete=models.SET_NULL, null=True, blank=True)

    visual_acuity_right = models.CharField(max_length=20, blank=True, null=True)
    visual_acuity_left = models.CharField(max_length=20, blank=True, null=True)

    intraocular_pressure_right = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    intraocular_pressure_left = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

    slit_lamp_findings = models.TextField(blank=True, null=True)
    fundus_exam_findings = models.TextField(blank=True, null=True)

    refraction_right = models.CharField(max_length=50, blank=True, null=True)
    refraction_left = models.CharField(max_length=50, blank=True, null=True)
    
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

    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Eye Exam - {self.patient.full_name} on {self.created_at.strftime('%Y-%m-%d')}"


class EyeFollowUp(models.Model):
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
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Follow-up for {self.patient.full_name} on {self.scheduled_date}"



