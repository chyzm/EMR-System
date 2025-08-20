# from time import timezone as tz
from django.utils import timezone as tz

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinLengthValidator
from django.conf import settings
from django.db.models import Sum
from django.forms import ValidationError
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey






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
        ('INSURANCE', 'HMO'),
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
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
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
    
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

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
    appointment_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'model__in': ('appointment', 'eyeappointment')}  # restrict to your models
    )
    appointment_object_id = models.PositiveIntegerField(null=True, blank=True)
    appointment = GenericForeignKey('appointment_content_type', 'appointment_object_id')
    services = models.ManyToManyField('ServicePriceList', blank=True, related_name='bills')  # <- added
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    service_date = models.DateField()
    due_date = models.DateField()
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name='created_bills'
    )
    updated_at = models.DateTimeField(auto_now=True)

    def get_balance(self):
        return self.amount - self.paid_amount

    def calculate_total(self):
        """Calculate total amount from selected services."""
        total = sum(service.price for service in self.services.all())
        self.amount = total
        self.save()
        return total


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
        
        
class ServicePriceList(models.Model):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - ₦{self.price}"
        
        
        



class ActionLog(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('LOGIN_FAILED', 'Login Failed'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    clinic = models.ForeignKey(Clinic, on_delete=models.SET_NULL, null=True, blank=True)  # Add clinic reference
    action = models.CharField(max_length=12, choices=ACTION_CHOICES)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    object_id = models.CharField(max_length=255, null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']  # Show most recent first
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['clinic']),
        ]

    def __str__(self):
        full_name = self.user.get_full_name() if self.user else "Unknown User"
        return f"{full_name} {self.action} {self.content_type} at {self.timestamp}"
    
    

class MedicationCategory(models.Model):
    """Categories for organizing medications"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    clinic = models.ForeignKey('Clinic', on_delete=models.CASCADE, related_name='medication_categories', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Medication Categories"
        # Don't add unique_together yet since we have null clinics
        
    def __str__(self):
        if self.clinic:
            return f"{self.name} ({self.clinic.name})"
        return self.name
    
    
    
class ClinicMedication(models.Model):
    """Clinic-specific medication inventory"""
    MEDICATION_TYPES = (
        ('TABLET', 'Tablet'),
        ('CAPSULE', 'Capsule'),
        ('SYRUP', 'Syrup'),
        ('INJECTION', 'Injection'),
        ('DROPS', 'Drops'),
        ('CREAM', 'Cream/Ointment'),
        ('LENS', 'Contact Lens'),
        ('GLASSES', 'Prescription Glasses'),
        ('OTHER', 'Other'),
    )
    
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('DISCONTINUED', 'Discontinued'),
    )
    
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='medications')
    name = models.CharField(max_length=200)
    generic_name = models.CharField(max_length=200, blank=True, null=True)
    category = models.ForeignKey(MedicationCategory, on_delete=models.SET_NULL, null=True, blank=True)
    medication_type = models.CharField(max_length=15, choices=MEDICATION_TYPES, default='TABLET')
    strength = models.CharField(max_length=50, blank=True, null=True)  # e.g., "500mg", "10ml"
    manufacturer = models.CharField(max_length=100, blank=True, null=True)
    
    # Inventory fields
    quantity_in_stock = models.PositiveIntegerField(default=0)
    minimum_stock_level = models.PositiveIntegerField(default=10)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    # Status and tracking
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='ACTIVE')
    expiry_date = models.DateField(blank=True, null=True)
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    
    # Metadata
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('clinic', 'name', 'strength')  # Prevent duplicate medications per clinic
        ordering = ['name']
    
    @property
    def is_out_of_stock(self):
        return self.quantity_in_stock == 0
    
    @property
    def is_low_stock(self):
        return self.quantity_in_stock <= self.minimum_stock_level and self.quantity_in_stock > 0
    
    @property
    def stock_status(self):
        if self.is_out_of_stock:
            return 'OUT_OF_STOCK'
        elif self.is_low_stock:
            return 'LOW_STOCK'
        return 'IN_STOCK'
    
    
    @property
    def total_price(self):
        """Unit price × stock quantity."""
        price = self.selling_price or 0
        qty = self.quantity_in_stock or 0
        return price * qty
    
    @property
    def display_name(self):
        if self.strength:
            return f"{self.name} ({self.strength})"
        return self.name
    
    def __str__(self):
        return f"{self.clinic.name} - {self.display_name}"



class Prescription(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='prescriptions')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='prescriptions')
    prescribed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='prescriptions')
    
    # Choice between clinic medication or custom entry
    clinic_medication = models.ForeignKey(ClinicMedication, on_delete=models.SET_NULL, null=True, blank=True, related_name='prescriptions')
    custom_medication = models.CharField(max_length=200, blank=True, null=True)  # For medications not in clinic inventory
    
    dosage = models.CharField(max_length=100)
    frequency = models.CharField(max_length=100)
    duration = models.CharField(max_length=100)
    quantity_prescribed = models.PositiveIntegerField(default=1)
    instructions = models.TextField(blank=True, null=True)
    
    date_prescribed = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    
    # Inventory tracking
    stock_deducted = models.BooleanField(default=False)  # Track if stock was deducted
    
    @property
    def medication_name(self):
        """Return either clinic medication or custom medication name"""
        if self.clinic_medication:
            return self.clinic_medication.display_name
        return self.custom_medication
    
    @property
    def is_from_inventory(self):
        """Check if prescription is from clinic inventory"""
        return self.clinic_medication is not None
    
    # @property
    # def total_price(self):
    #     """Return the total price (unit price * quantity)."""
    #     price = self.clinic_medication.selling_price or 0
    #     qty = self.quantity_prescribed or 0
    #     return price * qty
    
    
    def deduct_stock(self, bulk=False):
        """Deduct stock when prescription is dispensed.
        If bulk=True, skip creating individual billing."""
        if self.clinic_medication and not self.stock_deducted:
            if self.clinic_medication.quantity_in_stock >= self.quantity_prescribed:
                old_stock = self.clinic_medication.quantity_in_stock
                self.clinic_medication.quantity_in_stock -= self.quantity_prescribed
                self.clinic_medication.save()

                # Create stock movement record
                StockMovement.objects.create(
                    medication=self.clinic_medication,
                    movement_type='OUT',
                    quantity=-self.quantity_prescribed,
                    previous_stock=old_stock,
                    new_stock=self.clinic_medication.quantity_in_stock,
                    reference=f"Prescription #{self.id}",
                    created_by=self.prescribed_by,
                    notes=f"Dispensed to {self.patient.full_name}"
                )

                # Mark as dispensed
                self.stock_deducted = True
                self.save()

                # ✅ Only create billing if NOT bulk dispense
                if not bulk and self.clinic_medication.selling_price:
                    total_price = self.clinic_medication.selling_price * self.quantity_prescribed
                    Billing.objects.create(
                        patient=self.patient,
                        clinic=self.clinic,
                        appointment=None,  # or link to relevant appointment if exists
                        amount=total_price,
                        service_date=tz.now().date(),
                        due_date=tz.now().date(),
                        description=f"Dispensed {self.medication_name}",
                        created_by=self.prescribed_by
                    )

                return True
            else:
                return False  # Insufficient stock
        return None  # Not from inventory or already deducted


        
        def __str__(self):
            return f"{self.medication_name} for {self.patient.full_name}"
    
    
# Add these new models to your existing models.py






class StockMovement(models.Model):
    """Track stock movements for audit trail"""
    MOVEMENT_TYPES = (
        ('IN', 'Stock In'),
        ('OUT', 'Stock Out'),
        ('ADJUSTMENT', 'Stock Adjustment'),
        ('EXPIRED', 'Expired Stock'),
        ('DAMAGED', 'Damaged Stock'),
    )
    
    medication = models.ForeignKey(ClinicMedication, on_delete=models.CASCADE, related_name='stock_movements')
    movement_type = models.CharField(max_length=15, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField()  # Can be negative for OUT movements
    previous_stock = models.PositiveIntegerField()
    new_stock = models.PositiveIntegerField()
    notes = models.TextField(blank=True, null=True)
    reference = models.CharField(max_length=100, blank=True, null=True)  # e.g., prescription ID, supplier invoice
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.medication.display_name} - {self.movement_type} ({self.quantity})"


# Update your existing Prescription model


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='notifications', 
        null=True, 
        blank=True
    )
    clinic = models.ForeignKey(
        'Clinic', 
        on_delete=models.CASCADE, 
        related_name='notifications', 
        null=True, 
        blank=True
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.URLField(blank=True, null=True)
    object_id = models.CharField(max_length=50, blank=True, null=True)
    app_name = models.CharField(max_length=20, blank=True)  # 'medic', 'eye', etc.
    
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