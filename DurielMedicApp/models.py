from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from core.models import Patient, Clinic, Prescription
from django.utils import timezone
import uuid

class MedicalRecord(models.Model):
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='medical_records')
    encounter = models.ForeignKey('core.PatientEncounter', on_delete=models.SET_NULL, null=True, blank=True, related_name='general_records')

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
    
    
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, null=True, blank=True)
    appointment_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        limit_choices_to={'model__in': ('appointment', 'eyeappointment', 'dentalappointment')},
    )
    appointment_object_id = models.PositiveIntegerField(null=True, blank=True)
    appointment_object = GenericForeignKey('appointment_content_type', 'appointment_object_id')
    encounter = models.ForeignKey('core.PatientEncounter', on_delete=models.SET_NULL, null=True, blank=True, related_name='vitals')
    blood_pressure = models.CharField(max_length=10)
    pulse = models.IntegerField()
    temperature = models.FloatField()
    weight = models.FloatField()
    respiratory_rate = models.PositiveIntegerField(null=True, blank=True)
    oxygen_saturation = models.PositiveIntegerField(null=True, blank=True)
    height = models.FloatField(null=True, blank=True)
    bmi = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True)
    category = models.CharField(choices=[("CONSULT", "Consultation"), ("FOLLOWUP", "Follow-Up")], max_length=20)

    def set_appointment_object(self, appointment):
        self.appointment_object = appointment
        if isinstance(appointment, Appointment):
            self.appointment = appointment


class Admission(models.Model):
    ADMISSION_TYPES = (
        ('EMERGENCY', 'Emergency'),
        ('ELECTIVE', 'Elective'),
        ('REFERRAL', 'Referral'),
        ('OBSERVATION', 'Observation'),
        ('MATERNITY', 'Maternity'),
        ('SURGICAL', 'Surgical'),
    )
    ADMISSION_SOURCES = (
        ('OPD', 'Outpatient Department'),
        ('EMERGENCY', 'Emergency Unit'),
        ('REFERRAL', 'Referral'),
        ('TRANSFER', 'Transfer'),
        ('DIRECT', 'Direct Admission'),
    )
    STATUS_CHOICES = (
        ('ADMITTED', 'Admitted'),
        ('TRANSFERRED', 'Transferred'),
        ('DISCHARGED', 'Discharged'),
        ('REFERRED', 'Referred'),
        ('DECEASED', 'Deceased'),
        ('DAMA', 'Discharged Against Medical Advice'),
    )
    DISCHARGE_CONDITIONS = (
        ('STABLE', 'Stable'),
        ('IMPROVED', 'Improved'),
        ('UNCHANGED', 'Unchanged'),
        ('CRITICAL', 'Critical'),
        ('REFERRED', 'Referred'),
        ('DECEASED', 'Deceased'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='admissions')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='admissions', null=True, blank=True)
    encounter = models.ForeignKey('core.PatientEncounter', on_delete=models.SET_NULL, null=True, blank=True, related_name='admission_records')
    ward = models.CharField(max_length=50)
    bed = models.CharField(max_length=50, blank=True)
    admission_type = models.CharField(max_length=20, choices=ADMISSION_TYPES, default='EMERGENCY')
    admission_source = models.CharField(max_length=20, choices=ADMISSION_SOURCES, default='OPD')
    attending_doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admissions_attending',
    )
    provisional_diagnosis = models.TextField(blank=True)
    reason = models.TextField()
    admitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admissions_created',
    )
    date_admitted = models.DateTimeField(auto_now_add=True)
    expected_discharge_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ADMITTED')

    discharged = models.BooleanField(default=False)
    discharged_at = models.DateTimeField(null=True, blank=True)
    discharged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admissions_discharged',
    )
    discharge_diagnosis = models.TextField(blank=True)
    discharge_condition = models.CharField(max_length=20, choices=DISCHARGE_CONDITIONS, blank=True)
    discharge_summary = models.TextField(blank=True)
    discharge_instructions = models.TextField(blank=True)
    follow_up_plan = models.TextField(blank=True)

    class Meta:
        ordering = ['-date_admitted']
        indexes = [
            models.Index(fields=['clinic']),
            models.Index(fields=['discharged']),
            models.Index(fields=['-date_admitted']),
        ]

    def save(self, *args, **kwargs):
        if not self.clinic and self.patient_id:
            self.clinic = self.patient.clinic
        if self.discharged and self.status == 'ADMITTED':
            self.status = 'DISCHARGED'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Admission - {self.patient.full_name} ({self.ward})"


class MedicationAdministration(models.Model):
    STATUS_CHOICES = (
        ('GIVEN', 'Given'),
        ('HELD', 'Held'),
        ('REFUSED', 'Refused'),
        ('MISSED', 'Missed'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    admission = models.ForeignKey(Admission, on_delete=models.CASCADE, related_name='medication_administrations')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='medication_administrations')
    prescription = models.ForeignKey(
        'core.Prescription',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='administrations',
    )
    medication_name = models.CharField(max_length=200)
    dose = models.CharField(max_length=100)
    quantity_administered = models.PositiveIntegerField(default=1)
    route = models.CharField(max_length=50, blank=True)
    scheduled_time = models.DateTimeField(null=True, blank=True)
    administered_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='GIVEN')
    administered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    billing = models.ForeignKey(
        'core.Billing',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='medication_administrations',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-administered_at']
        indexes = [
            models.Index(fields=['admission', '-administered_at'], name='DurielMedic_med_adm_idx'),
            models.Index(fields=['patient', '-administered_at'], name='DurielMedic_med_pat_idx'),
        ]

    def save(self, *args, **kwargs):
        if self.admission_id and not self.patient_id:
            self.patient = self.admission.patient
        if self.prescription_id:
            self.medication_name = self.medication_name or self.prescription.medication_name
            self.dose = self.dose or self.prescription.dosage
        super().save(*args, **kwargs)


class AdmissionHandover(models.Model):
    HANDOVER_TYPES = (
        ('DOCTOR', 'Doctor Handover'),
        ('NURSE', 'Nurse Handover'),
        ('SHIFT', 'Shift Handover'),
        ('TRANSFER', 'Transfer Handover'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    admission = models.ForeignKey(Admission, on_delete=models.CASCADE, related_name='handovers')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='admission_handovers')
    handover_type = models.CharField(max_length=20, choices=HANDOVER_TYPES, default='SHIFT')
    summary = models.TextField()
    current_condition = models.TextField(blank=True)
    pending_tasks = models.TextField(blank=True)
    concerns = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='admission_handovers_given')
    receiving_staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='admission_handovers_received')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['admission', '-created_at'], name='DurielMedic_handov_adm_idx'),
            models.Index(fields=['patient', '-created_at'], name='DurielMedic_handov_pat_idx'),
        ]

    def save(self, *args, **kwargs):
        if self.admission_id and not self.patient_id:
            self.patient = self.admission.patient
        super().save(*args, **kwargs)


class FollowUp(models.Model):
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    session_count = models.PositiveIntegerField(default=0, blank=True)
    session_dates = models.TextField(blank=True, help_text="One physiotherapy session date per line.")
    additional_notes = models.TextField(blank=True, verbose_name="Additional Notes")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Physiotherapy Record for {self.patient.full_name} - {self.created_at.strftime('%Y-%m-%d')}"


class PhysiotherapyReferral(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    )
    PRIORITY_CHOICES = (
        ('ROUTINE', 'Routine'),
        ('URGENT', 'Urgent'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='physiotherapy_referrals')
    clinic = models.ForeignKey('core.Clinic', on_delete=models.CASCADE, related_name='physiotherapy_referrals')
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='physiotherapy_referrals')
    referred_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='physiotherapy_referrals_made')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='physiotherapy_referrals_assigned')
    reason = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='ROUTINE')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='PENDING')
    notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['clinic', 'status', '-created_at'], name='DurielMedic_phys_ref_q_idx'),
            models.Index(fields=['patient', '-created_at'], name='DurielMedic_phys_ref_pat_idx'),
        ]

    def __str__(self):
        return f"Physiotherapy referral for {self.patient.full_name} - {self.get_status_display()}"






