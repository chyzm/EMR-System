from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import (PatientListView, PatientDetailView, PatientCreateView,
                   AppointmentListView, AppointmentCreateView, StaffCreateView, PatientUpdateView)
from .views import PatientDeleteView
from .views import FollowUpListView, FollowUpCreateView, FollowUpUpdateView

app_name = 'DurielMedicApp'

urlpatterns = [
    # Authentication
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Role Management
    path('administration/manage-roles/', views.manage_user_roles, name='manage_roles'),
    path('administration/users/<int:user_id>/edit/', views.edit_user_role, name='edit_user_role'),

    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Patients
    path('patients/', PatientListView.as_view(), name='patient_list'),
    path('patients/<int:pk>/', PatientDetailView.as_view(), name='patient_detail'),
    path('patients/add/', PatientCreateView.as_view(), name='add_patient'),
    path('patients/<int:pk>/edit/', PatientUpdateView.as_view(), name='edit_patient'),
    path('patients/<int:pk>/delete/', PatientDeleteView.as_view(), name='delete_patient'),


    
    # Medical record
    path('patients/<int:patient_id>/medical-records/add/', views.add_medical_record, name='add_medical_record'),
    path('medical-records/<int:record_id>/edit/', views.edit_medical_record, name='edit_medical_record'),
    path('medical-records/<int:record_id>/delete/', views.delete_medical_record, name='delete_medical_record'),
    
    # Appointments
    path('appointments/', views.appointment_list, name='appointment_list'),
    path('appointments/create/', views.appointment_create, name='appointment_create'),
    path('appointments/<int:pk>/edit/', views.appointment_update, name='appointment_update'),
    path('appointments/add/', views.add_appointment, name='add_appointment'),
    path('appointments/<int:pk>/delete/', views.appointment_delete, name='appointment_delete'),
    path('appointments/<int:pk>/complete/', views.mark_appointment_completed, name='mark_completed'),
    path('appointments/<int:pk>/cancel/', views.mark_appointment_cancelled, name='mark_cancelled'),
    path('api/appointments/check/', views.check_appointment_availability, name='check_appointment_availability'),

    # Staff Management
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/add/', StaffCreateView.as_view(), name='add_staff'),
    
    # Notifications
    # path('notifications/mark-read/', views.mark_notifications_read, name='mark_notification_read'),
    path('notifications/mark-read/<int:pk>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/clear/', views.clear_notifications, name='clear_notifications'),
    
    # API endpoints for AJAX calls
    path('api/patients/', views.patient_search_api, name='patient_search_api'),
    
    
#   Prescription
    path('prescriptions/add/<int:patient_id>/', views.add_prescription, name='add_prescription'),
    path('prescriptions/edit/<int:pk>/', views.edit_prescription, name='edit_prescription'),
    path('prescriptions/', views.prescription_list, name='prescription_list'),
    path('prescriptions/deactivate/<int:pk>/', views.deactivate_prescription, name='deactivate_prescription'),
    
    
    # Vitals
    path('patients/<int:patient_id>/vitals/', views.record_vitals, name='record_vitals'),
    
    # Admission
    path('patients/<int:patient_id>/admit/', views.admit_patient, name='admit_patient'),
    path('patients/<int:patient_id>/discharge/', views.discharge_patient, name='discharge_patient'),
    
    # Patient status update
    path('patients/<int:patient_id>/ready-for-doctor/', views.mark_ready_for_doctor, name='ready_for_doctor'),
    
    # Consultation
    path('patients/<int:patient_id>/begin-consultation/', views.begin_consultation, name='begin_consultation'),
    path('patients/<int:patient_id>/complete-consultation/', views.complete_consultation, name='complete_consultation'),
    path('patients/<int:patient_id>/schedule-follow-up/', views.schedule_follow_up, name='schedule_follow_up'),
    
    # Follow Up
    path('follow-up/', FollowUpListView.as_view(), name='followup_list'),
    path('follow-up/new/', FollowUpCreateView.as_view(), name='followup_create'),
    path('follow-up/<int:pk>/edit/', FollowUpUpdateView.as_view(), name='followup_update'),
    path('follow-up/complete/<int:pk>/', views.complete_follow_up, name='complete_follow_up'),
    
    
    # Password reset
    path('password-reset/', auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html'), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),

    # Reports
    path('reports/generate/', views.generate_report, name='generate_report'),
    
    # Billing URLs
    path('billing/', views.billing_list, name='billing_list'),
    path('billing/create/', views.create_bill, name='create_bill'),
    path('billing/create/patient/<int:patient_id>/', views.create_bill, name='create_bill_for_patient'),
    path('billing/create/appointment/<int:appointment_id>/', views.create_bill, name='create_bill_for_appointment'),
    path('billing/<int:pk>/', views.view_bill, name='view_bill'),
    path('billing/<int:pk>/edit/', views.edit_bill, name='edit_bill'),
    path('billing/<int:pk>/payment/', views.record_payment, name='record_payment'),
    path('billing/<int:pk>/receipt/', views.generate_receipt, name='generate_receipt'),
    path('billing/<int:pk>/delete/', views.delete_bill, name='delete_bill'),
 ]
