from django.contrib import admin

from .models import (
    DentalAppointment,
    DentalExam,
    DentalFollowUp,
    DentalMedicalRecord,
    DentalProcedure,
    DentalTreatmentPlan,
)


@admin.register(DentalAppointment)
class DentalAppointmentAdmin(admin.ModelAdmin):
    list_display = ('patient', 'provider', 'visit_type', 'date', 'start_time', 'status')
    list_filter = ('clinic', 'status', 'visit_type', 'date')
    search_fields = ('patient__first_name', 'patient__last_name', 'patient__patient_id')


@admin.register(DentalExam)
class DentalExamAdmin(admin.ModelAdmin):
    list_display = ('patient', 'clinic', 'created_by', 'created_at')
    list_filter = ('clinic', 'created_at')
    search_fields = ('patient__first_name', 'patient__last_name', 'diagnosis')


@admin.register(DentalTreatmentPlan)
class DentalTreatmentPlanAdmin(admin.ModelAdmin):
    list_display = ('patient', 'title', 'priority', 'status', 'created_at')
    list_filter = ('clinic', 'priority', 'status')
    search_fields = ('patient__first_name', 'patient__last_name', 'title')


@admin.register(DentalProcedure)
class DentalProcedureAdmin(admin.ModelAdmin):
    list_display = ('patient', 'procedure_name', 'tooth_numbers', 'status', 'performed_at')
    list_filter = ('clinic', 'status', 'performed_at')
    search_fields = ('patient__first_name', 'patient__last_name', 'procedure_name', 'tooth_numbers')


@admin.register(DentalFollowUp)
class DentalFollowUpAdmin(admin.ModelAdmin):
    list_display = ('patient', 'scheduled_date', 'scheduled_time', 'completed')
    list_filter = ('clinic', 'completed', 'scheduled_date')
    search_fields = ('patient__first_name', 'patient__last_name', 'reason')


@admin.register(DentalMedicalRecord)
class DentalMedicalRecordAdmin(admin.ModelAdmin):
    list_display = ('patient', 'record_type', 'title', 'created_at')
    list_filter = ('clinic', 'record_type', 'created_at')
    search_fields = ('patient__first_name', 'patient__last_name', 'title')
