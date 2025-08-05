from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Clinic

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'clinic', 'is_staff')
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

# Optional: make clinics manageable too
@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone')
