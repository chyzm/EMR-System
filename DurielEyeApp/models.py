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

    # --- Standard eye-exam extensions (all optional / additive) ---
    # Pupils
    pupils_perrla = models.CharField(max_length=100, blank=True, null=True,
                                     help_text="PERRLA / pupil reactions")
    rapd_note = models.CharField(max_length=100, blank=True, null=True,
                                 help_text="Relative afferent pupillary defect (RAPD)")
    # Motility & alignment
    extraocular_motility = models.CharField(max_length=150, blank=True, null=True,
                                            help_text="Extraocular movements / motility")
    cover_test = models.CharField(max_length=150, blank=True, null=True,
                                  help_text="Cover test / phorias / tropias")
    confrontation_visual_fields = models.CharField(max_length=150, blank=True, null=True,
                                                   help_text="Confrontation visual fields")
    colour_vision = models.CharField(max_length=100, blank=True, null=True,
                                     help_text="Colour vision (e.g. Ishihara 14/14)")
    # IOP method / timing
    iop_method = models.CharField(max_length=50, blank=True, null=True,
                                  help_text="Tonometry method (Goldmann / NCT / Tono-pen)")
    iop_time = models.CharField(max_length=50, blank=True, null=True,
                                help_text="Time IOP measured")
    # Optic nerve head (cup-to-disc ratio)
    cup_disc_ratio_right = models.CharField(max_length=20, blank=True, null=True)
    cup_disc_ratio_left = models.CharField(max_length=20, blank=True, null=True)
    # Keratometry
    keratometry_right = models.CharField(max_length=50, blank=True, null=True)
    keratometry_left = models.CharField(max_length=50, blank=True, null=True)
    # Pachymetry (central corneal thickness)
    pachymetry_right = models.CharField(max_length=30, blank=True, null=True)
    pachymetry_left = models.CharField(max_length=30, blank=True, null=True)
    # Spectacle Rx prism / base (per eye)
    prism_right = models.CharField(max_length=30, blank=True, null=True)
    prism_left = models.CharField(max_length=30, blank=True, null=True)
    base_direction_right = models.CharField(max_length=30, blank=True, null=True)
    base_direction_left = models.CharField(max_length=30, blank=True, null=True)

    diagnosis = models.TextField(blank=True, null=True)
    treatment_plan = models.TextField(blank=True, null=True)
    procedure_notes = models.TextField(blank=True, null=True)
    imaging_results = models.TextField(blank=True, null=True)
    spectacle_or_contact_lens_plan = models.TextField(blank=True, null=True)
    frame_prescribed = models.BooleanField(default=False)
    frame_product = models.ForeignKey(
        'OpticalProduct',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='frame_exam_prescriptions',
        limit_choices_to={'product_type': 'FRAME'},
    )
    frame_prescription = models.TextField(blank=True, null=True)
    lens_prescribed = models.BooleanField(default=False)
    lens_product = models.ForeignKey(
        'OpticalProduct',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lens_exam_prescriptions',
        limit_choices_to={'product_type__in': ['SPECTACLE_LENS', 'CONTACT_LENS']},
    )
    lens_prescription = models.TextField(blank=True, null=True)
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



class OpticalProduct(models.Model):
    """Optical dispensary inventory (frames, lenses, contact lenses, accessories).

    Mirrors the ClinicMedication inventory pattern but carries optical-specific
    attributes, so it stays separate from the pharmacy drug catalogue.
    """
    PRODUCT_TYPES = (
        ('FRAME', 'Frame'),
        ('SPECTACLE_LENS', 'Spectacle Lens'),
        ('CONTACT_LENS', 'Contact Lens'),
        ('ACCESSORY', 'Accessory'),
    )
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('DISCONTINUED', 'Discontinued'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name='optical_products',
        limit_choices_to={'clinic_type': 'EYE'},
    )
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPES, default='FRAME')
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=120, blank=True, null=True)
    model_code = models.CharField(max_length=100, blank=True, null=True)
    colour = models.CharField(max_length=60, blank=True, null=True)
    size = models.CharField(max_length=60, blank=True, null=True)
    material = models.CharField(max_length=100, blank=True, null=True)

    # Optional stock-lens power attributes (for pre-made lenses / contact lenses)
    sphere = models.CharField(max_length=30, blank=True, null=True)
    cylinder = models.CharField(max_length=30, blank=True, null=True)
    axis = models.CharField(max_length=30, blank=True, null=True)

    # Inventory
    quantity_in_stock = models.PositiveIntegerField(default=0)
    minimum_stock_level = models.PositiveIntegerField(default=5)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    # Status and tracking
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='ACTIVE')
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    expiry_date = models.DateField(blank=True, null=True)

    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    @property
    def is_out_of_stock(self):
        return self.quantity_in_stock == 0

    @property
    def is_low_stock(self):
        return 0 < self.quantity_in_stock <= self.minimum_stock_level

    @property
    def stock_status(self):
        if self.is_out_of_stock:
            return 'OUT_OF_STOCK'
        if self.is_low_stock:
            return 'LOW_STOCK'
        return 'IN_STOCK'

    @property
    def total_price(self):
        return (self.selling_price or 0) * (self.quantity_in_stock or 0)

    @property
    def display_name(self):
        label = f"{self.brand} {self.name}".strip() if self.brand else self.name
        if self.model_code:
            label = f"{label} [{self.model_code}]"
        return label

    def __str__(self):
        return f"{self.clinic.name} - {self.display_name}"


class OpticalDispense(models.Model):
    """A dispense event for an optical product, billed like a pharmacy dispense."""
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='optical_dispenses')
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name='optical_dispenses',
        limit_choices_to={'clinic_type': 'EYE'},
    )
    encounter = models.ForeignKey(
        'core.PatientEncounter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='optical_dispenses',
    )
    appointment = models.ForeignKey(
        EyeAppointment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='optical_dispenses',
    )
    eye_exam = models.ForeignKey(
        EyeExam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='optical_dispenses',
        help_text="Source spectacle/contact-lens prescription, if any",
    )
    product = models.ForeignKey(OpticalProduct, on_delete=models.PROTECT, related_name='dispenses')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)

    dispensed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    dispensed_at = models.DateTimeField(auto_now_add=True)
    stock_deducted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-dispensed_at']

    @property
    def total_price(self):
        return (self.unit_price or 0) * (self.quantity or 0)

    def deduct_stock(self):
        """Decrement product stock and log an audit movement.

        Returns True on success, False if there is insufficient stock, and
        None if stock was already deducted for this dispense.
        """
        if self.stock_deducted:
            return None
        product = self.product
        if product.quantity_in_stock < self.quantity:
            return False
        old_stock = product.quantity_in_stock
        product.quantity_in_stock -= self.quantity
        product.save(update_fields=['quantity_in_stock', 'updated_at'])

        OpticalStockMovement.objects.create(
            product=product,
            movement_type='OUT',
            quantity=-self.quantity,
            previous_stock=old_stock,
            new_stock=product.quantity_in_stock,
            reference=f"Optical Dispense #{self.id}",
            created_by=self.dispensed_by,
            notes=f"Dispensed to {self.patient.full_name}",
        )

        self.stock_deducted = True
        self.save(update_fields=['stock_deducted'])
        return True

    def __str__(self):
        return f"{self.product.display_name} x{self.quantity} for {self.patient.full_name}"


class OpticalPrescriptionRequest(models.Model):
    """Work queue item for frame/lens prescriptions sent to the optician."""
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('ACKNOWLEDGED', 'Acknowledged'),
        ('PROCESSED', 'Processed'),
        ('DISPENSED', 'Dispensed'),
        ('CANCELLED', 'Cancelled'),
    )

    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='optical_prescription_requests')
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name='optical_prescription_requests',
        limit_choices_to={'clinic_type': 'EYE'},
    )
    appointment = models.ForeignKey(
        EyeAppointment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='optical_prescription_requests',
    )
    eye_exam = models.OneToOneField(
        EyeExam,
        on_delete=models.CASCADE,
        related_name='optical_prescription_request',
    )
    frame_product = models.ForeignKey(
        OpticalProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='frame_prescription_requests',
    )
    frame_prescription = models.TextField(blank=True, null=True)
    lens_product = models.ForeignKey(
        OpticalProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lens_prescription_requests',
    )
    lens_prescription = models.TextField(blank=True, null=True)
    optician_note = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')

    prescribed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_optical_prescription_requests',
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_optical_prescription_requests',
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_optical_prescription_requests',
    )
    dispensed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dispensed_optical_prescription_requests',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(blank=True, null=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    dispensed_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', '-created_at']

    @property
    def requested_items(self):
        items = []
        if self.frame_product or self.frame_prescription:
            items.append('frame')
        if self.lens_product or self.lens_prescription:
            items.append('lens')
        return ', '.join(items) or 'optical item'

    def __str__(self):
        return f"{self.patient.full_name} - {self.requested_items} ({self.get_status_display()})"


class OpticalStockMovement(models.Model):
    """Audit trail for optical inventory movements (separate from pharmacy StockMovement)."""
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    MOVEMENT_TYPES = (
        ('IN', 'Stock In'),
        ('OUT', 'Stock Out'),
        ('ADJUSTMENT', 'Stock Adjustment'),
        ('EXPIRED', 'Expired Stock'),
        ('DAMAGED', 'Damaged Stock'),
    )

    product = models.ForeignKey(OpticalProduct, on_delete=models.CASCADE, related_name='stock_movements')
    movement_type = models.CharField(max_length=15, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField()  # Negative for OUT movements
    previous_stock = models.PositiveIntegerField()
    new_stock = models.PositiveIntegerField()
    notes = models.TextField(blank=True, null=True)
    reference = models.CharField(max_length=100, blank=True, null=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.display_name} - {self.movement_type} ({self.quantity})"



