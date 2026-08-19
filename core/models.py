# from time import timezone as tz
from django.utils import timezone as tz
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.db import models, transaction
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinLengthValidator
from django.conf import settings
from django.db.models import Sum
from django.forms import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
import uuid






class Clinic(models.Model):
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    subscription_type = models.CharField(
        max_length=10,
        choices=(('TRIAL','Trial'), ('MONTHLY', 'Monthly'), ('YEARLY', 'Yearly')),
        null=True, blank=True
    )
    subscription_start_date = models.DateField(null=True, blank=True)
    subscription_end_date = models.DateField(null=True, blank=True)
    is_subscription_active = models.BooleanField(default=False)
    last_reminder_sent = models.CharField(
        max_length=8,
        choices=(('NONE', 'None'), ('D14', '14 days'), ('D7', '7 days'), ('D0', 'Expiry day')),
        default='NONE'
    ) 
    
    
    def __str__(self):
        return f"{self.get_clinic_type_display()} - {self.name}"
    
    def days_until_expiration(self):
        if not self.subscription_end_date:
            return None
        return (self.subscription_end_date - tz.now().date()).days

    def subscription_end_for(self, plan_type: str, preserve_remaining=True):
        """Calculate an expiry date without discarding already-paid days."""
        TRIAL_DAYS = 14  # set to 7 if you want a 7-day trial
        today = tz.now().date()
        if plan_type == 'TRIAL':
            return today + timedelta(days=TRIAL_DAYS)
        base_date = today
        if preserve_remaining and self.subscription_end_date and self.subscription_end_date > today:
            base_date = self.subscription_end_date
        if plan_type == 'MONTHLY':
            return base_date + timedelta(days=30)
        if plan_type == 'YEARLY':
            return base_date + timedelta(days=365)
        raise ValueError(f'Unsupported subscription plan: {plan_type}')

    def set_subscription(self, plan_type: str, preserve_remaining=True):
        today = tz.now().date()
        self.subscription_type = plan_type
        self.subscription_start_date = today
        self.subscription_end_date = self.subscription_end_for(plan_type, preserve_remaining=preserve_remaining)
        self.is_subscription_active = True
        self.last_reminder_sent = 'NONE'
        self.save(update_fields=[
            'subscription_type','subscription_start_date','subscription_end_date',
            'is_subscription_active','last_reminder_sent'
        ])

class CustomUser(AbstractUser):
    username = models.CharField(
        max_length=150,
        unique=True,
        help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.',
        validators=[AbstractUser.username_validator],
        error_messages={'unique': 'username not accepted'},
    )
    email = models.EmailField(unique=True, blank=True, null=True)

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
        ('PHARMACIST', 'Pharmacist'),
        ('OPTOMETRIST', 'Optometrist'),
        ('OPTICIAN', 'Optician'),
        ('DENTIST', 'Dentist'),
        ('PHYSIOTHERAPIST', 'Physiotherapist'),
        ('RECEPTIONIST', 'Receptionist'),
        ('LAB_TECHNICIAN', 'Lab Technician'),
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

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    def __str__(self):
        return self.display_name

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
    
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
            with transaction.atomic():
                self.clinic = Clinic.objects.select_for_update().get(pk=self.clinic_id)
                clinic_code = ''.join(self.clinic.name.upper().split())[:3]
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
            return
        if not self.created_at:
            self.created_at = tz.now()
        super().save(*args, **kwargs)
        
        
    from django.db.models import Sum

    def get_outstanding_balance(self):
        from django.db.models import Sum, F, Case, When, DecimalField, ExpressionWrapper
        effective_amount = Case(
            When(discount_type__in=['PERCENTAGE', 'FIXED'], then=F('final_amount')),
            When(final_amount__gt=0, then=F('final_amount')),
            default=F('amount'),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
        outstanding = ExpressionWrapper(
            effective_amount - F('paid_amount'),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
        result = self.bills.aggregate(total=Sum(outstanding))
        return result['total']
    
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

    DISCOUNT_TYPE_CHOICES = (
        ('NONE', 'No Discount'),
        ('PERCENTAGE', 'Percentage'),
        ('FIXED', 'Fixed Amount'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='bills')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='bills')
    appointment_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'model__in': ('appointment', 'eyeappointment', 'dentalappointment')}
    )
    appointment_object_id = models.PositiveIntegerField(null=True, blank=True)
    appointment = GenericForeignKey('appointment_content_type', 'appointment_object_id')
    encounter = models.ForeignKey(
        'PatientEncounter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bills',
    )
    services = models.ManyToManyField('ServicePriceList', blank=True, related_name='bills')
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    service_date = models.DateField()
    due_date = models.DateField()
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    # Discount fields
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES, default='NONE')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Percentage (0-100) or fixed amount")
    discount_reason = models.CharField(max_length=255, blank=True)
    discount_applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='applied_discounts'
    )
    discount_applied_at = models.DateTimeField(null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    final_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_bills'
    )
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_discount(self):
        """Calculate discount amount based on type and value"""
        from decimal import Decimal
        if self.discount_type == 'PERCENTAGE':
            self.discount_amount = (self.amount * self.discount_value) / Decimal('100')
        elif self.discount_type == 'FIXED':
            self.discount_amount = min(self.discount_value, self.amount)
        else:
            self.discount_amount = Decimal('0.00')
        return self.discount_amount

    def calculate_final_amount(self):
        """Calculate final amount after discount"""
        self.calculate_discount()
        self.final_amount = self.amount - self.discount_amount
        return self.final_amount

    def get_effective_amount(self):
        """
        Amount due after discount.

        Uses stored final_amount when a discount is applied (even if it becomes 0),
        and falls back to amount for legacy records where final_amount may be 0.
        """
        if self.discount_type != 'NONE' or self.discount_amount > 0 or self.discount_value > 0:
            return self.final_amount
        if self.final_amount and self.final_amount > 0:
            return self.final_amount
        return self.amount

    def get_balance(self):
        """Get balance based on final amount (after discount)"""
        return self.get_effective_amount() - self.paid_amount

    def calculate_total(self):
        """Calculate total amount from selected services."""
        total = sum(service.price for service in self.services.all())
        self.amount = total
        self.calculate_final_amount()
        self.save()
        return total

    def _as_decimal(self, value, default=Decimal('0.00')):
        try:
            return Decimal(value)
        except (InvalidOperation, TypeError, ValueError):
            return default

    def save(self, *args, **kwargs):
        self.amount = self._as_decimal(self.amount)
        self.discount_value = self._as_decimal(self.discount_value)
        self.discount_amount = self._as_decimal(self.discount_amount)
        self.final_amount = self._as_decimal(self.final_amount)
        self.paid_amount = self._as_decimal(self.paid_amount)

        if self.amount > 0:
            self.calculate_final_amount()
        elif self.final_amount == 0:
            self.final_amount = self.amount
        super().save(*args, **kwargs)


class BillingLineItem(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('BILLED', 'Billed'),
        ('VOIDED', 'Voided'),
    )
    SOURCE_CHOICES = (
        ('APPOINTMENT', 'Appointment'),
        ('CONSULTATION', 'Consultation'),
        ('LAB', 'Lab'),
        ('PRESCRIPTION', 'Prescription'),
        ('PROCEDURE', 'Procedure'),
        ('ADMISSION', 'Admission'),
        ('PHYSIO_CONSULTATION', 'Physiotherapy Consultation'),
        ('PHYSIO_SESSION', 'Physiotherapy Session'),
        ('TREATMENT', 'Treatment'),
        ('OPTICAL', 'Optical'),
        ('MANUAL', 'Manual'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='billing_line_items')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='billing_line_items')
    bill = models.ForeignKey(Billing, on_delete=models.SET_NULL, null=True, blank=True, related_name='line_items')
    appointment_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='billing_line_items_for_appointment',
        limit_choices_to={'model__in': ('appointment', 'eyeappointment', 'dentalappointment')},
    )
    appointment_object_id = models.PositiveIntegerField(null=True, blank=True)
    appointment = GenericForeignKey('appointment_content_type', 'appointment_object_id')
    encounter = models.ForeignKey('PatientEncounter', on_delete=models.SET_NULL, null=True, blank=True, related_name='billing_line_items')
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='MANUAL')
    source_content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True, related_name='billing_line_items_for_source')
    source_object_id = models.CharField(max_length=255, null=True, blank=True)
    source_object = GenericForeignKey('source_content_type', 'source_object_id')
    service = models.ForeignKey('ServicePriceList', on_delete=models.SET_NULL, null=True, blank=True, related_name='billing_line_items')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_billing_line_items')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_billing_line_items')
    approved_at = models.DateTimeField(null=True, blank=True)
    billed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at', 'id']
        indexes = [
            models.Index(fields=['clinic', 'status'], name='core_bi_clinic_status_idx'),
            models.Index(fields=['patient', 'status'], name='core_bi_patient_status_idx'),
            models.Index(fields=['appointment_content_type', 'appointment_object_id'], name='core_billitem_appt_idx'),
            models.Index(fields=['source_content_type', 'source_object_id'], name='core_billitem_source_idx'),
        ]

    def save(self, *args, **kwargs):
        self.quantity = Decimal(self.quantity or 0)
        self.unit_price = Decimal(self.unit_price or 0)
        self.total_amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def approve(self, user):
        self.status = 'APPROVED'
        self.approved_by = user
        self.approved_at = tz.now()
        self.save(update_fields=['status', 'approved_by', 'approved_at', 'total_amount', 'updated_at'])

    def mark_billed(self, bill):
        self.bill = bill
        self.status = 'BILLED'
        self.billed_at = tz.now()
        self.save(update_fields=['bill', 'status', 'billed_at', 'total_amount', 'updated_at'])

    def __str__(self):
        return f"{self.description} - {self.patient.full_name} ({self.get_status_display()})"


class PatientEncounter(models.Model):
    ENCOUNTER_TYPES = (
        ('GENERAL_CONSULTATION', 'General Consultation'),
        ('EYE_CONSULTATION', 'Eye Consultation'),
        ('DENTAL_CONSULTATION', 'Dental Consultation'),
        ('EMERGENCY', 'Emergency'),
        ('ADMISSION', 'Admission'),
        ('FOLLOW_UP', 'Follow-Up'),
        ('PROCEDURE', 'Procedure'),
    )
    STATUS_CHOICES = (
        ('OPEN', 'Open'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('DISCHARGED', 'Discharged'),
        ('CANCELLED', 'Cancelled'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='encounters')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='encounters')
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='encounters')
    encounter_type = models.CharField(max_length=25, choices=ENCOUNTER_TYPES)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='OPEN')
    appointment_content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    appointment_object_id = models.PositiveIntegerField(null=True, blank=True)
    appointment = GenericForeignKey('appointment_content_type', 'appointment_object_id')
    admission = models.ForeignKey('DurielMedicApp.Admission', on_delete=models.SET_NULL, null=True, blank=True, related_name='encounters')
    started_at = models.DateTimeField(default=tz.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_encounters')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-started_at', '-id']
        indexes = [
            models.Index(fields=['clinic', 'patient', '-started_at'], name='core_enc_clinic_patient_idx'),
            models.Index(fields=['clinic', 'status'], name='core_enc_clinic_status_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['appointment_content_type', 'appointment_object_id'],
                name='core_unique_appointment_encounter',
                condition=models.Q(appointment_content_type__isnull=False, appointment_object_id__isnull=False),
            ),
            models.UniqueConstraint(
                fields=['admission'],
                name='core_unique_admission_encounter',
                condition=models.Q(admission__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{self.get_encounter_type_display()} - {self.patient.full_name}"


class Payment(models.Model):
    PAYMENT_METHODS = (
        ('CASH', 'Cash'),
        ('CARD', 'Card'),
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('MOBILE_MONEY', 'Mobile Money'),
        ('CHEQUE', 'Cheque'),
        ('OTHER', 'Other'),
    )
    
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - ₦{self.price}"


class SyncOperation(models.Model):
    STATUS_CHOICES = (
        ('PROCESSING', 'Processing'),
        ('SYNCED', 'Synced'),
        ('FAILED', 'Failed'),
    )

    operation_id = models.UUIDField(unique=True, editable=False)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='sync_operations')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    device_id = models.CharField(max_length=64)
    action = models.CharField(max_length=50)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='PROCESSING')
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['clinic', 'status', 'created_at'], name='core_syncop_clinic_status_idx'),
            models.Index(fields=['device_id', 'created_at'], name='core_syncop_device_created_idx'),
        ]
        
        
class ServerSyncOutbox(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('SYNCING', 'Syncing'),
        ('SYNCED', 'Synced'),
        ('FAILED', 'Failed'),
    )

    operation_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='server_sync_outbox')
    model_label = models.CharField(max_length=120)
    action = models.CharField(max_length=20)
    record_sync_id = models.UUIDField(null=True, blank=True)
    origin_node_id = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='PENDING')
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['clinic', 'status', 'created_at'], name='core_srvout_clinic_status_idx'),
            models.Index(fields=['model_label', 'record_sync_id'], name='core_srvout_model_record_idx'),
        ]


class ServerSyncChange(models.Model):
    operation_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='server_sync_changes')
    model_label = models.CharField(max_length=120)
    action = models.CharField(max_length=20)
    record_sync_id = models.UUIDField(null=True, blank=True)
    origin_node_id = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['clinic', 'id'], name='core_srvchg_clinic_id_idx'),
            models.Index(fields=['origin_node_id', 'id'], name='core_srvchg_origin_id_idx'),
        ]


class ServerSyncState(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['key']

        



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
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='prescriptions')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='prescriptions')
    prescribed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='prescriptions',
    )
    admission = models.ForeignKey(
        'DurielMedicApp.Admission',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prescriptions',
    )
    encounter = models.ForeignKey(
        PatientEncounter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prescriptions',
    )
    
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
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification = models.ForeignKey('Notification', on_delete=models.CASCADE)
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'notification')


# ========================================
# Laboratory / Diagnostic Models
# ========================================

def lab_result_upload_path(instance, filename):
    """Upload path for lab result files: media/lab_results/{patient_id}/{filename}"""
    return f'lab_results/{instance.lab_test_order.patient.patient_id}/{filename}'


def validate_file_size(value):
    """Validate file size is under 5MB"""
    limit = 5 * 1024 * 1024  # 5MB
    if value.size > limit:
        raise ValidationError('File size must be under 5MB.')


class LabTestCategory(models.Model):
    """Categories for organizing lab tests (e.g., Blood Tests, Urine Tests, Imaging)"""
    CATEGORY_TYPES = (
        ('BLOOD', 'Blood Tests'),
        ('URINE', 'Urine Tests'),
        ('IMAGING', 'Imaging/Radiology'),
        ('MICROBIOLOGY', 'Microbiology'),
        ('BIOCHEMISTRY', 'Biochemistry'),
        ('PATHOLOGY', 'Pathology'),
        ('CARDIOLOGY', 'Cardiology Tests'),
        ('OTHER', 'Other'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='lab_categories')
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=20, choices=CATEGORY_TYPES, default='OTHER')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Lab Test Categories"
        unique_together = ('clinic', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"


class LabTest(models.Model):
    """Catalog of available lab tests at a clinic"""
    SAMPLE_TYPES = (
        ('BLOOD', 'Blood'),
        ('URINE', 'Urine'),
        ('STOOL', 'Stool'),
        ('SALIVA', 'Saliva'),
        ('TISSUE', 'Tissue'),
        ('SWAB', 'Swab'),
        ('NONE', 'No Sample Required'),
        ('OTHER', 'Other'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='lab_tests')
    category = models.ForeignKey(LabTestCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='tests')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True, help_text="Unique test code for this clinic")
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sample_type = models.CharField(max_length=20, choices=SAMPLE_TYPES, default='BLOOD')
    turnaround_time = models.CharField(max_length=100, blank=True, help_text="e.g., '24 hours', '3-5 days'")
    preparation_instructions = models.TextField(blank=True, help_text="Patient preparation instructions")
    reference_range = models.TextField(blank=True, help_text="Normal reference range for this test")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('clinic', 'code')
        ordering = ['category', 'name']

    def __str__(self):
        if self.code:
            return f"{self.code} - {self.name}"
        return self.name


class LabTestOrder(models.Model):
    """Order for lab tests - links patient/appointment to ordered tests"""
    STATUS_CHOICES = (
        ('ORDERED', 'Ordered'),
        ('IN_QUEUE', 'In Queue'),
        ('SAMPLE_COLLECTED', 'Sample Collected'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('REVIEWED', 'Reviewed by Doctor'),
        ('CANCELLED', 'Cancelled'),
    )

    PRIORITY_CHOICES = (
        ('ROUTINE', 'Routine'),
        ('URGENT', 'Urgent'),
        ('STAT', 'STAT (Immediate)'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='lab_orders')
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name='lab_orders')

    # Generic relation to appointment (can be Appointment or EyeAppointment)
    appointment_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'model__in': ('appointment', 'eyeappointment', 'dentalappointment')}
    )
    appointment_object_id = models.PositiveIntegerField(null=True, blank=True)
    appointment = GenericForeignKey('appointment_content_type', 'appointment_object_id')
    encounter = models.ForeignKey(
        PatientEncounter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lab_orders',
    )

    # Ordered tests
    ordered_tests = models.ManyToManyField(LabTest, related_name='orders')

    # Order details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ORDERED')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='ROUTINE')
    clinical_notes = models.TextField(blank=True, help_text="Clinical notes from ordering doctor")
    diagnosis = models.TextField(blank=True, help_text="Suspected diagnosis")

    # Staff tracking
    ordered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='lab_orders_created'
    )
    sample_collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lab_samples_collected'
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lab_orders_reviewed'
    )

    # Timestamps
    ordered_at = models.DateTimeField(auto_now_add=True)
    sample_collected_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # Billing reference (optional - for auto-billing)
    billing = models.ForeignKey(
        'Billing',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lab_orders'
    )

    class Meta:
        ordering = ['-ordered_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
            models.Index(fields=['-ordered_at']),
        ]

    def __str__(self):
        return f"Lab Order #{self.pk} - {self.patient.full_name} ({self.get_status_display()})"

    @property
    def total_price(self):
        """Calculate total price of all ordered tests"""
        return sum(test.price for test in self.ordered_tests.all())

    @property
    def is_complete(self):
        """Check if all results have been entered"""
        return self.results.count() == self.ordered_tests.count()

    def mark_sample_collected(self, collected_by):
        """Mark sample as collected"""
        self.status = 'SAMPLE_COLLECTED'
        self.sample_collected_by = collected_by
        self.sample_collected_at = tz.now()
        self.save()

    def mark_processing(self):
        """Mark order as processing"""
        self.status = 'PROCESSING'
        self.save()

    def mark_completed(self):
        """Mark order as completed"""
        self.status = 'COMPLETED'
        self.completed_at = tz.now()
        self.save()

    def mark_reviewed(self, reviewed_by):
        """Mark order as reviewed by doctor"""
        self.status = 'REVIEWED'
        self.reviewed_by = reviewed_by
        self.reviewed_at = tz.now()
        self.save()


class LabTestResult(models.Model):
    """Individual test results within a lab order"""
    from django.core.validators import FileExtensionValidator

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    lab_test_order = models.ForeignKey(LabTestOrder, on_delete=models.CASCADE, related_name='results')
    test = models.ForeignKey(LabTest, on_delete=models.CASCADE, related_name='results')

    # Result data
    result_value = models.TextField(blank=True, help_text="Test result value/findings")
    reference_range = models.CharField(max_length=200, blank=True, help_text="Normal reference range")
    unit = models.CharField(max_length=50, blank=True, help_text="Unit of measurement")
    is_abnormal = models.BooleanField(default=False, help_text="Flag if result is outside normal range")

    # Result file (PDF, images)
    result_file = models.FileField(
        upload_to=lab_result_upload_path,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png']),
            validate_file_size
        ],
        help_text="Upload result document (PDF, JPG, PNG - max 5MB)"
    )

    # Notes
    result_notes = models.TextField(blank=True, help_text="Additional notes about the result")
    technician_comments = models.TextField(blank=True, help_text="Lab technician comments")

    # Staff tracking
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='lab_results_performed'
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lab_results_verified'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('lab_test_order', 'test')
        ordering = ['test__name']

    def __str__(self):
        return f"{self.test.name} result for Order #{self.lab_test_order.pk}"

    @property
    def has_file(self):
        """Check if result has an uploaded file"""
        return bool(self.result_file)
