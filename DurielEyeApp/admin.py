from django.contrib import admin

from .models import EyeAppointment, EyeExam, EyeFollowUp, EyeMedicalRecord


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
