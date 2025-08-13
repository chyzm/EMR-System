from time import timezone as tz
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinLengthValidator
from django.conf import settings
from django.db.models import Sum
from django.forms import ValidationError


class Clinic(models.Model):
    CLINIC_TYPES = (
        ('GENERAL', 'General Clinic'),
        ('EYE', 'Eye Clinic'),
        ('DENTAL', 'Dental Clinic'),
    )
    
    name = models.CharField(max_length=100)
    clinic_type = models.CharField(max_length=10, choices=CLINIC_TYPES)
    address = models.TextField()
    phone = models.CharField(max_length=15)
    email = models.EmailField()
    website = models.URLField(blank=True, null=True)
    logo = models.ImageField(upload_to='clinic_logos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.get_clinic_type_display()} - {self.name}"

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
    
    role = models.CharField(max_length=15, choices=ROLES, default='DOCTOR')
    verified = models.BooleanField(default=False)
    clinic = models.ManyToManyField(Clinic, related_name='staff')
    primary_clinic = models.ForeignKey(Clinic, on_delete=models.SET_NULL, null=True, blank=True, related_name='primary_staff')
    title = models.CharField(max_length=10, choices=TITLE_CHOICES, blank=True, null=True)
    license_number = models.CharField(max_length=50, blank=True, null=True)
    specialization = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='staff_profiles/', blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    last_activity = models.DateTimeField(auto_now=True)

class Patient(models.Model):
    BLOOD_GROUPS = (
        ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-'),
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
    patient_id = models.CharField(max_length=10, primary_key=True, unique=True, editable=False)
    # clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='patients')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='patients')
    full_name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, null=True)
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

    # def save(self, *args, **kwargs):
    #     if not self.clinic:
    #         raise ValueError("Patient must be assigned to a clinic before saving.")

    #     if self.patient_id is None:
    #         last_patient = Patient.objects.filter(clinic=self.clinic).order_by('-patient_id').first()
    #         self.patient_id = (last_patient.patient_id + 1) if last_patient else 100001

    #     super().save(*args, **kwargs)
    
    def save(self, *args, **kwargs):
        if not self.patient_id:
            if not self.clinic:
                raise ValueError("Patient must be assigned to a clinic before saving")
            # Get clinic code (first 3 letters of clinic name, uppercase, no spaces)
            clinic_code = ''.join(self.clinic.name.upper().split())[:3]
            # Find last patient for this clinic
            last_patient = Patient.objects.filter(
                clinic=self.clinic,
                patient_id__startswith=clinic_code
            ).order_by('-created_at').first()
            if last_patient and last_patient.patient_id[3:].isdigit():
                next_number = int(last_patient.patient_id[3:]) + 1
            else:
                next_number = 1
            self.patient_id = f"{clinic_code}{next_number:06d}"
        if not self.created_at:
            self.created_at = tz.now()
        super().save(*args, **kwargs)
        
        
    from django.db.models import Sum

    def get_outstanding_balance(self):
        from django.db.models import Sum, F
        result = self.bills.aggregate(total=Sum(F('amount') - F('paid_amount')))
        return result['total']  # Remove the "or 0" to return None when no bills exist
    
    def has_billing_records(self):
        return self.bills.exists()   # Assuming a reverse relation exists

    
        
    def __str__(self):
        return f"{self.full_name} (ID: {self.patient_id})"



class Billing(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PAID', 'Paid'),
        ('PARTIAL', 'Partially Paid'),
        ('CANCELLED', 'Cancelled'),
    )
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='bills')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='bills')
    appointment = models.ForeignKey('DurielMedicApp.Appointment', on_delete=models.SET_NULL, null=True, blank=True, related_name='bill')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    service_date = models.DateField()
    due_date = models.DateField()
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_bills')
    updated_at = models.DateTimeField(auto_now=True)

    def get_balance(self):
        return self.amount - self.paid_amount

class Payment(models.Model):
    PAYMENT_METHODS = (
        ('CASH', 'Cash'),
        ('CARD', 'Card'),
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('MOBILE_MONEY', 'Mobile Money'),
        ('CHEQUE', 'Cheque'),
        ('OTHER', 'Other'),
    )
    
    billing = models.ForeignKey(Billing, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='CASH')
    transaction_reference = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['-payment_date']
