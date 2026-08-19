from django.contrib import admin

from .models import (EyeAppointment, EyeExam, EyeFollowUp, EyeMedicalRecord,
                     OpticalProduct, OpticalDispense, OpticalPrescriptionRequest,
                     OpticalStockMovement)


@admin.register(EyeAppointment)
class EyeAppointmentAdmin(admin.ModelAdmin):
    list_display = ('patient', 'provider', 'clinic', 'date', 'start_time', 'status', 'payment_type')
    list_filter = ('clinic', 'status', 'payment_type', 'date')
    search_fields = ('patient__patient_id', 'patient__first_name', 'patient__last_name', 'provider__username', 'reason')
    list_select_related = ('patient', 'provider', 'clinic')
    date_hierarchy = 'date'
    readonly_fields = ('sync_id', 'created_at', 'updated_at')


@admin.register(EyeExam)
class EyeExamAdmin(admin.ModelAdmin):
    list_display = ('patient', 'appointment', 'visual_acuity_right', 'visual_acuity_left', 'created_by', 'created_at')
    list_filter = ('appointment__clinic', 'created_at')
    search_fields = ('patient__patient_id', 'patient__first_name', 'patient__last_name', 'slit_lamp_findings', 'fundus_exam_findings')
    list_select_related = ('patient', 'appointment', 'created_by')
    date_hierarchy = 'created_at'
    readonly_fields = ('sync_id', 'created_at')


@admin.register(EyeMedicalRecord)
class EyeMedicalRecordAdmin(admin.ModelAdmin):
    list_display = ('patient', 'clinic', 'record_type', 'title', 'created_by', 'created_at')
    list_filter = ('clinic', 'record_type', 'created_at')
    search_fields = ('patient__patient_id', 'patient__first_name', 'patient__last_name', 'title', 'description')
    list_select_related = ('patient', 'clinic', 'created_by')
    date_hierarchy = 'created_at'
    readonly_fields = ('sync_id', 'created_at', 'updated_at')


@admin.register(EyeFollowUp)
class EyeFollowUpAdmin(admin.ModelAdmin):
    list_display = ('patient', 'clinic', 'scheduled_date', 'scheduled_time', 'completed', 'created_by')
    list_filter = ('clinic', 'completed', 'scheduled_date')
    search_fields = ('patient__patient_id', 'patient__first_name', 'patient__last_name', 'reason', 'notes')
    list_select_related = ('patient', 'clinic', 'created_by')
    date_hierarchy = 'scheduled_date'
    readonly_fields = ('sync_id', 'created_at')


@admin.register(OpticalProduct)
class OpticalProductAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'clinic', 'product_type', 'quantity_in_stock',
                    'minimum_stock_level', 'selling_price', 'status')
    list_filter = ('clinic', 'product_type', 'status')
    search_fields = ('name', 'brand', 'model_code', 'colour', 'material')
    list_select_related = ('clinic', 'added_by')
    readonly_fields = ('sync_id', 'created_at', 'updated_at')


@admin.register(OpticalDispense)
class OpticalDispenseAdmin(admin.ModelAdmin):
    list_display = ('product', 'patient', 'clinic', 'quantity', 'unit_price',
                    'stock_deducted', 'dispensed_by', 'dispensed_at')
    list_filter = ('clinic', 'stock_deducted', 'dispensed_at')
    search_fields = ('patient__patient_id', 'patient__first_name', 'patient__last_name',
                     'product__name', 'product__brand')
    list_select_related = ('patient', 'clinic', 'product', 'dispensed_by')
    date_hierarchy = 'dispensed_at'
    readonly_fields = ('sync_id', 'dispensed_at')


@admin.register(OpticalPrescriptionRequest)
class OpticalPrescriptionRequestAdmin(admin.ModelAdmin):
    list_display = ('patient', 'clinic', 'requested_items', 'status', 'prescribed_by', 'created_at')
    list_filter = ('clinic', 'status', 'created_at')
    search_fields = (
        'patient__patient_id',
        'patient__first_name',
        'patient__last_name',
        'frame_prescription',
        'lens_prescription',
        'optician_note',
    )
    list_select_related = ('patient', 'clinic', 'eye_exam', 'prescribed_by')
    date_hierarchy = 'created_at'
    readonly_fields = ('sync_id', 'created_at', 'updated_at')


@admin.register(OpticalStockMovement)
class OpticalStockMovementAdmin(admin.ModelAdmin):
    list_display = ('product', 'movement_type', 'quantity', 'previous_stock',
                    'new_stock', 'created_by', 'created_at')
    list_filter = ('movement_type', 'created_at')
    search_fields = ('product__name', 'product__brand', 'reference', 'notes')
    list_select_related = ('product', 'created_by')
    date_hierarchy = 'created_at'
    readonly_fields = ('sync_id', 'created_at')
