from django.contrib import admin

from .models import (
    Admission,
    AdmissionHandover,
    Appointment,
    FollowUp,
    MedicalRecord,
    MedicationAdministration,
    PhysiotherapyRecord,
    Vitals,
)


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('patient', 'provider', 'clinic', 'date', 'start_time', 'status', 'payment_type')
    list_filter = ('clinic', 'status', 'payment_type', 'date')
    search_fields = ('patient__patient_id', 'patient__first_name', 'patient__last_name', 'provider__username', 'reason')
    list_select_related = ('patient', 'provider', 'clinic')
    date_hierarchy = 'date'
    readonly_fields = ('sync_id', 'created_at', 'updated_at')


@admin.register(Vitals)
class VitalsAdmin(admin.ModelAdmin):
    list_display = ('appointment', 'patient_name', 'blood_pressure', 'pulse', 'temperature', 'weight', 'category')
    list_filter = ('appointment__clinic', 'category')
    search_fields = ('appointment__patient__patient_id', 'appointment__patient__first_name', 'appointment__patient__last_name')
    list_select_related = ('appointment', 'appointment__patient')
    readonly_fields = ('sync_id',)

    @admin.display(description='Patient', ordering='appointment__patient__last_name')
    def patient_name(self, obj):
        return obj.appointment.patient.full_name


@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    list_display = ('patient', 'diagnosis_summary', 'created_by', 'created_at', 'updated_at')
    list_filter = ('patient__clinic', 'created_at')
    search_fields = ('patient__patient_id', 'patient__first_name', 'patient__last_name', 'diagnosis', 'chief_complaint')
    list_select_related = ('patient', 'created_by')
    date_hierarchy = 'created_at'
    readonly_fields = ('sync_id', 'created_at', 'updated_at')

    @admin.display(description='Diagnosis')
    def diagnosis_summary(self, obj):
        return obj.diagnosis[:80]


@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = ('patient', 'clinic', 'ward', 'bed', 'admission_type', 'attending_doctor', 'date_admitted', 'status')
    list_filter = ('clinic', 'status', 'admission_type', 'admission_source', 'discharged', 'date_admitted')
    search_fields = ('patient__patient_id', 'patient__first_name', 'patient__last_name', 'ward', 'bed', 'provisional_diagnosis')
    list_select_related = ('patient', 'clinic', 'attending_doctor', 'admitted_by', 'discharged_by')
    date_hierarchy = 'date_admitted'
    readonly_fields = ('sync_id', 'date_admitted')


@admin.register(MedicationAdministration)
class MedicationAdministrationAdmin(admin.ModelAdmin):
    list_display = ('patient', 'admission', 'medication_name', 'dose', 'quantity_administered', 'route', 'status', 'billing', 'administered_by', 'administered_at')
    list_filter = ('patient__clinic', 'status', 'route', 'administered_at')
    search_fields = ('patient__patient_id', 'patient__first_name', 'patient__last_name', 'medication_name', 'dose')
    list_select_related = ('patient', 'admission', 'prescription', 'billing', 'administered_by')
    date_hierarchy = 'administered_at'
    readonly_fields = tuple(field.name for field in MedicationAdministration._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AdmissionHandover)
class AdmissionHandoverAdmin(admin.ModelAdmin):
    list_display = ('patient', 'admission', 'handover_type', 'created_by', 'receiving_staff', 'created_at')
    list_filter = ('patient__clinic', 'handover_type', 'created_at')
    search_fields = ('patient__patient_id', 'patient__first_name', 'patient__last_name', 'summary', 'pending_tasks', 'concerns')
    list_select_related = ('patient', 'admission', 'created_by', 'receiving_staff')
    date_hierarchy = 'created_at'
    readonly_fields = ('sync_id', 'created_at')


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ('patient', 'scheduled_date', 'scheduled_time', 'completed', 'created_by', 'created_at')
    list_filter = ('patient__clinic', 'completed', 'scheduled_date')
    search_fields = ('patient__patient_id', 'patient__first_name', 'patient__last_name', 'reason', 'notes')
    list_select_related = ('patient', 'created_by')
    date_hierarchy = 'scheduled_date'
    readonly_fields = ('sync_id', 'created_at')


@admin.register(PhysiotherapyRecord)
class PhysiotherapyRecordAdmin(admin.ModelAdmin):
    list_display = ('patient', 'diagnosis_summary', 'created_by', 'created_at', 'updated_at')
    list_filter = ('patient__clinic', 'created_at')
    search_fields = ('patient__patient_id', 'patient__first_name', 'patient__last_name', 'diagnosis', 'treatment_plan', 'progress_notes')
    list_select_related = ('patient', 'created_by')
    date_hierarchy = 'created_at'
    readonly_fields = ('sync_id', 'created_at', 'updated_at')

    @admin.display(description='Diagnosis')
    def diagnosis_summary(self, obj):
        return obj.diagnosis[:80]
