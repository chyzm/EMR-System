from django.urls import path
from . import views
from .views import (
    EyeAppointmentListView, EyeAppointmentCreateView,
    EyeFollowUpListView, EyeFollowUpCreateView, EyeFollowUpUpdateView
)

app_name = 'DurielEyeApp'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.eye_dashboard, name='eye_dashboard'),

    # Medical records
    path('patients/<str:patient_id>/medical_records/add/', views.add_eye_medical_record, name='add_medical_record'),
    path('medical_records/<int:record_id>/edit/', views.edit_eye_medical_record, name='edit_eye_medical_record'),
    path('medical_records/<int:record_id>/delete/', views.delete_eye_medical_record, name='delete_eye_medical_record'),

    # Appointments
    path('appointments/', EyeAppointmentListView.as_view(), name='appointment_list'),
    path('appointments/create/', EyeAppointmentCreateView.as_view(), name='appointment_create'),
    # path('appointments/<int:pk>/edit/', views.eye_appointment_update, name='appointment_update'),
    path('appointments/<int:appointment_id>/edit/', views.eye_appointment_update, name='appointment_update'),

    path('appointments/<int:pk>/', views.eye_appointment_detail, name='appointment_detail'),
    # path('appointments/add/', views.add_eye_appointment, name='add_appointment'),
    path('appointments/<int:pk>/delete/', views.eye_appointment_delete, name='appointment_delete'),
    path('appointments/<int:pk>/complete/', views.mark_eye_appointment_completed, name='mark_completed'),
    path('appointments/<int:pk>/cancel/', views.mark_eye_appointment_cancelled, name='mark_cancelled'),
    path('api/appointments/check/', views.check_eye_appointment_availability, name='check_appointment_availability'),

    # Eye Exams
    path('appointments/<int:appointment_id>/record-exam/',views.record_eye_exam,name='record_eye_exam'),
    path('exams/<int:exam_id>/edit/',views.edit_eye_exam, name='edit_eye_exam'),
    path('exams/<int:exam_id>/delete/', views.delete_eye_exam, name='delete_eye_exam'),
    


    # Notifications
    path('notifications/mark-read/<int:pk>/', views.mark_eye_notification_read, name='mark_notification_read'),
    path('notifications/clear/', views.clear_eye_notifications, name='clear_notifications'),

    # Consultation flow
    path('patients/<str:patient_id>/begin-consultation/', views.begin_eye_consultation, name='begin_consultation'),
    path('patients/<str:patient_id>/complete-consultation/', views.complete_eye_consultation, name='complete_consultation'),
    path('patients/<str:patient_id>/schedule-follow-up/', views.schedule_eye_follow_up, name='schedule_follow_up'),

    # Follow Up
    path('follow-up/', EyeFollowUpListView.as_view(), name='followup_list'),
    path('follow-up/new/', EyeFollowUpCreateView.as_view(), name='followup_create'),
    path('follow-up/<int:pk>/edit/', EyeFollowUpUpdateView.as_view(), name='followup_update'),
    path('follow-up/complete/<int:pk>/', views.complete_eye_follow_up, name='complete_eye_follow_up'),


    # Reports
    path('reports/generate/', views.generate_eye_report, name='generate_report'),
    
    
  
]
