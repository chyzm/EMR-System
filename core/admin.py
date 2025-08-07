from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
# from .models import CustomUser, Clinic
from .models import CustomUser, Clinic


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


# Optional: make clinics manageable too
@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone')
