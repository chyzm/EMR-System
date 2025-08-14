from django.urls import path
from . import views
from .views import (AppointmentListView, AppointmentCreateView,
                   FollowUpListView, FollowUpCreateView, FollowUpUpdateView)
from core.views import PatientDetailView


app_name = 'DurielMedicApp'

urlpatterns = [
    
    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Medical records
    path('patients/<str:patient_id>/medical-records/add/', views.add_medical_record, name='add_medical_record'),
    path('medical-records/<int:record_id>/edit/', views.edit_medical_record, name='edit_medical_record'),
    path('medical-records/<int:record_id>/delete/', views.delete_medical_record, name='delete_medical_record'),
    
    # Appointments
    path('appointments/', AppointmentListView.as_view(), name='appointment_list'),
    path('appointments/create/', AppointmentCreateView.as_view(), name='appointment_create'),
    path('appointments/<int:pk>/edit/', views.appointment_update, name='appointment_update'),
    path('appointments/<int:pk>/', views.appointment_detail, name='appointment_detail'),
    path('appointments/add/', views.add_appointment, name='add_appointment'),
    path('appointments/<int:pk>/delete/', views.appointment_delete, name='appointment_delete'),
    path('appointments/<int:pk>/complete/', views.mark_appointment_completed, name='mark_completed'),
    path('appointments/<int:pk>/cancel/', views.mark_appointment_cancelled, name='mark_cancelled'),
    path('api/appointments/check/', views.check_appointment_availability, name='check_appointment_availability'),

    # Notifications
    # path('notifications/mark-read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-read/<int:pk>/', views.mark_notification_read, name='mark_notification_read'),
    # path('notifications/mark-read/<int:notification_id>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/clear/', views.clear_notifications, name='clear_notifications'),
    
    
    
    # Vitals
    path('patients/<str:patient_id>/vitals/', views.record_vitals, name='record_vitals'),
    path('patients/<str:patient_id>/vitals/', views.record_vitals, name='record_vitals'),

    # Admission
    path('patients/<int:patient_id>/admit/', views.admit_patient, name='admit_patient'),
    path('patients/<int:patient_id>/discharge/', views.discharge_patient, name='discharge_patient'),
    
    # Patient status
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
    
    
    # Reports
    path('reports/generate/', views.generate_report, name='generate_report'),
]