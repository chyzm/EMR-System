from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinLengthValidator
from django.conf import settings
import uuid


class CustomUser(AbstractUser):
    TITLE_CHOICES = (
        ('Dr.', 'Dr.'),
        ('PT.', 'PT.'),
        ('Nr.', 'Nr.'),
        ('Mr.', 'Mr.'),
        ('Mrs.', 'Mrs.'),
        ('Miss.', 'Miss.'),
    )
    
    ROLES = (
        ('ADMIN', 'Administrator'),
        ('DOCTOR', 'Doctor'),
        ('NURSE', 'Nurse'),
        ('OPTOMETRIST', 'Optometrist'),
        ('PHYSIOTHERAPIST', 'Physiotherapist'),
        ('RECEPTIONIST', 'Receptionist'),
    )
    
    CLINIC = (
        ('DURIEL_CLINIC', 'duriel clinic'),
    )
    
    
    
    role = models.CharField(max_length=15, choices=ROLES, default='DOCTOR')
    clinic = models.ForeignKey('Clinic', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    title = models.CharField(max_length=10, choices=TITLE_CHOICES, blank=True, null=True)
    license_number = models.CharField(max_length=50, blank=True, null=True)
    specialization = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='staff_profiles/', blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    last_activity = models.DateTimeField(auto_now=True)
    
    class Meta:
        permissions = [
            ("can_view_all_patients", "Can view all patients"),
            ("can_edit_patient_records", "Can edit patient records"),
            ("can_delete_patient_records", "Can delete patient records"),
            ("can_create_prescriptions", "Can create prescriptions"),
            ("can_view_reports", "Can view reports"),
            ("can_manage_staff", "Can manage staff"),
        ]

class Clinic(models.Model):
 
    
    
    name = models.CharField(max_length=100)
    address = models.TextField()
    phone = models.CharField(max_length=15)
    email = models.EmailField()
    website = models.URLField(blank=True, null=True)
    logo = models.ImageField(upload_to='clinic_logos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name

class Patient(models.Model):
    BLOOD_GROUPS = (
        ('A+', 'A+'),
        ('A-', 'A-'),
        ('B+', 'B+'),
        ('B-', 'B-'),
        ('AB+', 'AB+'),
        ('AB-', 'AB-'),
        ('O+', 'O+'),
        ('O-', 'O-'),
    )
    
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    )
    
    STATUS_CHOICES = (
        ('REGISTERED', 'Registered at Front Desk'),
        ('VITALS_TAKEN', 'Vitals Recorded'),
        ('IN_CONSULTATION', 'In Consultation'),
        ('ADMITTED', 'Admitted'),
        ('FOLLOW_UP', 'Scheduled for Follow-up'),
        ('FOLLOW_UP_COMPLETE', 'Follow-up Complete'),
        ('DISCHARGED', 'Discharged'),
        ('CONSULTATION_COMPLETE', 'Consultation Complete'),
    )
    
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='REGISTERED')
    patient_id = models.PositiveIntegerField(primary_key=True, unique=True, editable=False)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='patients', null=True, blank=True)
    full_name = models.CharField(max_length=200)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUPS, blank=True, null=True)
    allergies = models.TextField(blank=True, null=True)
    contact = models.CharField(max_length=15, validators=[MinLengthValidator(10)])
    address = models.TextField()
    emergency_contact = models.CharField(max_length=15, validators=[MinLengthValidator(10)])
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='patient_profiles/', blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_patients')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.patient_id is None:
            last_patient = Patient.objects.order_by('-patient_id').first()
            if last_patient and last_patient.patient_id:
                self.patient_id = last_patient.patient_id + 1
            else:
                self.patient_id = 100001  # Starting ID
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} (ID: {self.patient_id})"


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
    
    
# class OptometryTest(models.Model):
#     patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
#     visual_acuity = models.CharField(max_length=20)
#     refraction = models.TextField()
#     notes = models.TextField()

# class PhysiotherapyTest(models.Model):
#     patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
#     diagnosis = models.TextField()
#     session_notes = models.TextField()
#     therapy_plan = models.TextField()






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

class Billing(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PAID', 'Paid'),
        ('PARTIAL', 'Partially Paid'),
        ('CANCELLED', 'Cancelled'),
    )
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='bills')
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='bill')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    service_date = models.DateField()
    due_date = models.DateField()
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Bill #{self.id} - {self.patient.full_name} - {self.status}"

class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.URLField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Notification for {self.user.username}"