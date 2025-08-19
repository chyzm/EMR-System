from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import (PatientListView, PatientDetailView, PatientCreateView,
                   StaffCreateView, PatientUpdateView, PatientDeleteView, CustomLoginView)
from core.views import select_clinic
from django.shortcuts import redirect
from .views import admin_dashboard, activate_user, set_staff, set_superuser, verify_user, add_clinic, ClinicUpdateView
from .views import activity_log, clear_activity_log, bulk_delete_logs
from .views import mark_notification_read, clear_notifications



app_name = 'core'

urlpatterns = [
    
    path('select-clinic/', select_clinic, name='select_clinic'),
    
    # Authentication
    path('', lambda request: redirect('login'), name='home_redirect'),
    # path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('login/', CustomLoginView.as_view(), name='login'),  # ✅ Changed this line
    path('logout/', views.logout_view, name='logout'),
    
    # Role Management
    path('administration/manage-roles/', views.manage_user_roles, name='manage_roles'),
    path('administration/users/<int:user_id>/edit/', views.edit_user_role, name='edit_user_role'),

    # Patients
    path('patients/', PatientListView.as_view(), name='patient_list'),
    path('patients/add/', PatientCreateView.as_view(), name='add_patient'),
    path('patients/<str:pk>/', PatientDetailView.as_view(), name='patient_detail'),  # <-- changed
    path('patients/<str:pk>/edit/', PatientUpdateView.as_view(), name='edit_patient'),  # <-- changed
    path('patients/<str:pk>/delete/', PatientDeleteView.as_view(), name='delete_patient'),  # <-- changed

    # Staff Management
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/add/', StaffCreateView.as_view(), name='add_staff'),
    

    # API endpoints
    path('api/patients/', views.patient_search_api, name='patient_search_api'),
    
    
    # Password reset
    path('password-reset/', auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html'), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),

  
    
    # Billing
    path('billing/', views.billing_list, name='billing_list'),
    path('billing/create/', views.create_bill, name='create_bill'),
    # path('billing/create/patient/<int:patient_id>/', views.create_bill, name='create_bill_for_patient'),
    path('billing/create/patient/<str:patient_id>/', views.create_bill, name='create_bill_for_patient'),
    path('billing/create/appointment/<int:appointment_id>/', views.create_bill, name='create_bill_for_appointment'),
    path('billing/<int:pk>/', views.view_bill, name='view_bill'),
    path('billing/<int:pk>/edit/', views.edit_bill, name='edit_bill'),
    path('billing/<int:pk>/payment/', views.record_payment, name='record_payment'),
    path('billing/<int:pk>/receipt/', views.generate_receipt, name='generate_receipt'),
    path('billing/<int:pk>/delete/', views.delete_bill, name='delete_bill'),
    
    # Prescriptions
    path('prescriptions/add/<str:patient_id>/', views.add_prescription, name='add_prescription'),
    path('prescriptions/edit/<int:pk>/', views.edit_prescription, name='edit_prescription'),
    path('prescriptions/', views.prescription_list, name='prescription_list'),
    path('prescriptions/deactivate/<int:pk>/', views.deactivate_prescription, name='deactivate_prescription'),
    path('prescriptions/delete/<int:pk>/', views.delete_prescription, name='delete_prescription'),
    path("prescriptions/menu/", views.prescription_menu, name="prescription_menu"),

    
    
    # AI assist
    path("api/ai-chat/", views.ai_chat, name="ai_chat"),
    
    
    
    path('select-clinic/', views.select_clinic, name='select_clinic'),
    
    # admin dashboard
    path('dashboard/', admin_dashboard, name='admin_dashboard'),
    path('activate-user/<int:user_id>/', activate_user, name='activate_user'),
    path('set-staff/<int:user_id>/', set_staff, name='set_staff'),
    path('set-superuser/<int:user_id>/', set_superuser, name='set_superuser'),
    path('verify-user/<int:user_id>/', verify_user, name='verify_user'),
    path('add-clinic/', add_clinic, name='add_clinic'),
    path('clinics/<int:pk>/edit/', ClinicUpdateView.as_view(), name='edit_clinic'),
    path('clinics/<int:pk>/delete/', views.delete_clinic, name='delete_clinic'),
    
    
    # settings
    path('settings/', views.settings_view, name='settings'),
    
    
    path('toggle-superuser/<int:user_id>/', views.toggle_superuser, name='toggle_superuser'),
    path('toggle-staff/<int:user_id>/', views.toggle_staff, name='toggle_staff'),
    path('toggle-verify/<int:user_id>/', views.toggle_verify, name='toggle_verify'),
    
    # Activity Log
    path('activity-log/', activity_log, name='activity_log'),
    path('activity-log/clear/', clear_activity_log, name='clear_activity_log'),
    path('activity-log/bulk-delete/', bulk_delete_logs, name='bulk_delete_logs'),
    
    # Notification
     path('notifications/mark-read/<int:pk>/', mark_notification_read, name='mark_notification_read'),
     path('notifications/clear/', clear_notifications, name='clear_notifications'),
     
     
     # Inventory Dashboard
    path('inventory/', views.inventory_dashboard, name='inventory_dashboard'),
    
    # Medication Management
    path('inventory/medications/', views.medication_list, name='medication_list'),
    path('inventory/medications/add/', views.add_medication, name='add_medication'),
    path('inventory/medications/<int:pk>/edit/', views.edit_medication, name='edit_medication'),
    path('inventory/medications/<int:pk>/detail/', views.medication_detail, name='medication_detail'),
    path('inventory/medications/<int:pk>/delete/', views.delete_medication, name='delete_medication'),
    
    # Stock Management
    path('inventory/medications/<int:pk>/adjust-stock/', views.adjust_stock, name='adjust_stock'),
    path('inventory/medications/<int:pk>/movements/', views.stock_movements, name='stock_movements'),
    path('inventory/bulk-upload/', views.bulk_upload_stock, name='bulk_upload_stock'),
    path('inventory/low-stock-report/', views.low_stock_report, name='low_stock_report'),
    
    # Enhanced Prescriptions
    # path('patients/<str:patient_id>/prescriptions/add-enhanced/', views.enhanced_add_prescription, name='enhanced_add_prescription'),
    path('prescriptions/<int:pk>/dispense/', views.dispense_prescription, name='dispense_prescription'),
    path("prescriptions/bulk-dispense/", views.bulk_dispense, name="bulk_dispense"),
 
    
    # Category Management
    path('inventory/categories/', views.manage_categories, name='manage_categories'),
    
    # API Endpoints
    path('api/medications/search/', views.medication_search_api, name='medication_search_api'),
    path('api/medications/<int:pk>/stock/', views.check_medication_stock, name='check_medication_stock'),
    
    # Export stock to csv
    path('medications/export/csv/', views.export_medications_csv, name='export_medications_csv'),
    
    
    # Service Price List Management
    path('services/', views.service_list, name='service_list'),
    path('services/add/', views.add_service, name='add_service'),
    path('services/<int:pk>/edit/', views.edit_service, name='edit_service'),
    path('services/<int:pk>/delete/', views.delete_service, name='delete_service'),
    path('services/toggle/<int:pk>/', views.toggle_service_status, name='toggle_service_status'),
]