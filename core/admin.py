from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.db import models
from django.utils import timezone
# from .models import CustomUser, Clinic
from .models import CustomUser, Clinic
from .models import (
    Patient, Billing, ServicePriceList, Prescription,
    MedicationCategory, ClinicMedication, StockMovement,
    LabTestCategory, LabTest, LabTestOrder, LabTestResult,
    ActionLog, Notification, NotificationRead,
    PaymentTransaction, PendingClinicRegistration,
)


# @admin.register(CustomUser)
# class CustomUserAdmin(UserAdmin):
#     model = CustomUser
#     list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'clinic', 'is_staff')
#     fieldsets = UserAdmin.fieldsets + (
#         ('Extra Fields', {
#             'fields': ('role', 'clinic', 'license_number', 'specialization', 'phone', 'profile_picture', 'is_verified')
#         }),
#     )
#     add_fieldsets = UserAdmin.add_fieldsets + (
#         ('Extra Fields', {
#             'fields': ('role', 'clinic', 'license_number', 'specialization', 'phone', 'profile_picture'),
#         }),
#     )

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'get_clinic', 'is_staff')
    list_filter = ('role',)
    ordering = ('primary_clinic__name', 'username')

    def get_clinic(self, obj):
        # If it's ManyToMany
        if hasattr(obj.clinic, 'all'):
            return ", ".join([c.name for c in obj.clinic.all()])
        # If it's ForeignKey
        return obj.clinic.name if obj.clinic else "-"
    get_clinic.short_description = 'Clinic'

    fieldsets = UserAdmin.fieldsets + (
        ('Extra Fields', {
            'fields': ('role', 'clinic', 'license_number', 'specialization', 'phone', 'profile_picture', 'is_verified')
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Extra Fields', {
            'fields': ('role', 'clinic', 'license_number', 'specialization', 'phone', 'profile_picture'),
        }),
    )


# Simple filter to filter by clinic even for M2M users
class ClinicListFilter(admin.SimpleListFilter):
    title = 'clinic'
    parameter_name = 'clinic'

    def lookups(self, request, model_admin):
        clinics = Clinic.objects.all()
        return [(c.id, c.name) for c in clinics]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(clinic__id=self.value())
        return queryset

# Attach the ClinicListFilter to CustomUserAdmin so users can be filtered by clinic
CustomUserAdmin.list_filter = ('role', ClinicListFilter)


# Optional: make clinics manageable too
@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone')
    ordering = ('name',)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('patient_id', 'full_name', 'clinic', 'contact', 'date_of_birth')
    search_fields = ('patient_id', 'first_name', 'last_name', 'contact')
    list_filter = ('clinic', 'gender')
    ordering = ('clinic__name', 'last_name', 'first_name')


@admin.register(Billing)
class BillingAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient', 'clinic', 'amount', 'paid_amount', 'status', 'service_date')
    list_filter = ('status', 'clinic')
    search_fields = ('patient__first_name', 'patient__last_name', 'id')
    actions = ['mark_paid']
    ordering = ('clinic__name', '-created_at', '-service_date', '-id')

    def mark_paid(self, request, queryset):
        updated = queryset.update(status='PAID', paid_amount=models.F('final_amount'))
        self.message_user(request, f"Marked {updated} bill(s) as PAID")
    mark_paid.short_description = 'Mark selected bills as PAID'


@admin.register(ServicePriceList)
class ServicePriceListAdmin(admin.ModelAdmin):
    list_display = ('name', 'clinic', 'price', 'is_active')
    list_filter = ('clinic', 'is_active')
    search_fields = ('name',)
    ordering = ('clinic__name', 'name')


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'clinic', 'email', 'plan_type', 'amount', 'currency', 'provider', 'status', 'paid_at', 'created_at')
    list_filter = ('status', 'provider', 'plan_type', 'currency', 'created_at')
    search_fields = ('reference', 'email', 'clinic__name')
    readonly_fields = ('reference', 'provider_response', 'paid_at', 'created_at', 'updated_at')
    ordering = ('-created_at',)


@admin.register(PendingClinicRegistration)
class PendingClinicRegistrationAdmin(admin.ModelAdmin):
    list_display = ('clinic_name', 'email', 'username', 'payment', 'expires_at', 'completed_at', 'created_at')
    list_filter = ('clinic_type', 'completed_at', 'expires_at')
    search_fields = ('clinic_name', 'email', 'username', 'payment__reference')
    readonly_fields = ('payment', 'password_hash', 'registration_payload', 'created_at', 'updated_at')
    ordering = ('-created_at',)


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient', 'prescribed_by', 'date_prescribed', 'is_active')
    list_filter = ('is_active', 'prescribed_by', 'patient__clinic')
    search_fields = ('patient__first_name', 'patient__last_name')
    actions = ('deactivate_selected',)
    ordering = ('patient__clinic__name', '-date_prescribed', '-id')

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    @admin.action(description='Deactivate selected prescriptions')
    def deactivate_selected(self, request, queryset):
        updated = queryset.filter(is_active=True).update(is_active=False, deactivated_at=timezone.now())
        self.message_user(request, f'Deactivated {updated} prescription(s).')


@admin.register(MedicationCategory)
class MedicationCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'clinic', 'created_at')
    search_fields = ('name',)
    list_filter = ('clinic',)
    ordering = ('clinic__name', 'name')


@admin.register(ClinicMedication)
class ClinicMedicationAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'clinic', 'quantity_in_stock', 'selling_price', 'status')
    list_filter = ('clinic', 'status')
    search_fields = ('name', 'generic_name')
    ordering = ('clinic__name', 'name', 'strength')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('medication', 'movement_type', 'quantity', 'previous_stock', 'new_stock', 'created_by', 'created_at')
    search_fields = ('medication__name',)
    list_filter = ('medication__clinic', 'movement_type')
    ordering = ('medication__clinic__name', '-created_at')


# ---------- Lab Admin ----------
class LabTestResultInline(admin.TabularInline):
    model = LabTestResult
    extra = 0
    readonly_fields = ('result_file_link',)

    def result_file_link(self, obj):
        if obj and obj.result_file:
            return format_html('<a href="{}" target="_blank">Download</a>', obj.result_file.url)
        return '-'
    result_file_link.short_description = 'Result File'


@admin.register(LabTestCategory)
class LabTestCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'clinic', 'category_type', 'is_active')
    list_filter = ('clinic', 'category_type', 'is_active')
    search_fields = ('name',)
    ordering = ('clinic__name', 'name')


@admin.register(LabTest)
class LabTestAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'clinic', 'category', 'sample_type', 'price', 'is_active')
    list_filter = ('clinic', 'category', 'sample_type', 'is_active')
    search_fields = ('name', 'code')
    actions = ['make_active', 'make_inactive']
    ordering = ('clinic__name', 'name')

    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Marked {updated} test(s) as active")
    make_active.short_description = 'Mark selected tests as Active'

    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Marked {updated} test(s) as inactive")
    make_inactive.short_description = 'Mark selected tests as Inactive'


@admin.register(LabTestOrder)
class LabTestOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient', 'clinic', 'status', 'priority', 'ordered_by', 'ordered_at', 'total_price')
    list_filter = ('status', 'priority', 'clinic', 'ordered_by')
    search_fields = ('patient__first_name', 'patient__last_name', 'id')
    inlines = [LabTestResultInline]
    actions = ['mark_completed', 'mark_reviewed']
    ordering = ('clinic__name', '-ordered_at', '-id')

    def mark_completed(self, request, queryset):
        updated = queryset.update(status='COMPLETED')
        self.message_user(request, f"Marked {updated} order(s) as Completed")
    mark_completed.short_description = 'Mark selected orders as Completed'

    def mark_reviewed(self, request, queryset):
        updated = queryset.update(status='REVIEWED')
        self.message_user(request, f"Marked {updated} order(s) as Reviewed")
    mark_reviewed.short_description = 'Mark selected orders as Reviewed'


@admin.register(LabTestResult)
class LabTestResultAdmin(admin.ModelAdmin):
    list_display = ('test', 'lab_test_order', 'performed_by', 'created_at', 'has_file')
    list_filter = ('performed_by', 'lab_test_order__clinic')
    search_fields = ('test__name', 'lab_test_order__patient__first_name')
    readonly_fields = ('result_file_link',)
    ordering = ('lab_test_order__clinic__name', '-created_at')

    def result_file_link(self, obj):
        if obj and obj.result_file:
            return format_html('<a href="{}" target="_blank">Download</a>', obj.result_file.url)
        return '-'
    result_file_link.short_description = 'Result File'


@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'content_type', 'object_id')
    search_fields = ('user__username', 'details')
    list_filter = ('action',)
    ordering = ('clinic__name', '-timestamp')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('message', 'user', 'clinic', 'is_read', 'created_at')
    list_filter = ('is_read', 'clinic')
    search_fields = ('message',)
    ordering = ('clinic__name', '-created_at')


@admin.register(NotificationRead)
class NotificationReadAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification', 'read_at')
