from django.urls import path

from . import views


app_name = 'DurielDentalApp'

urlpatterns = [
    path('dashboard/', views.dental_dashboard, name='dental_dashboard'),
    path('appointments/', views.DentalAppointmentListView.as_view(), name='appointment_list'),
    path('appointments/create/', views.DentalAppointmentCreateView.as_view(), name='appointment_create'),
    path('appointments/<int:pk>/', views.appointment_detail, name='appointment_detail'),
    path('appointments/<int:pk>/edit/', views.DentalAppointmentUpdateView.as_view(), name='appointment_update'),
    path('appointments/<int:pk>/status/<str:status>/', views.update_appointment_status, name='appointment_status'),
    path('api/appointments/today-count/', views.today_appointment_count, name='today_appointment_count'),
    path('patients/<str:patient_id>/chart/', views.patient_dental_chart, name='patient_chart'),
    path('patients/<str:patient_id>/exam/', views.record_exam, name='record_exam'),
    path('patients/<str:patient_id>/treatment-plan/', views.create_treatment_plan, name='create_treatment_plan'),
    path('patients/<str:patient_id>/procedure/', views.record_procedure, name='record_procedure'),
    path('patients/<str:patient_id>/follow-up/', views.schedule_follow_up, name='schedule_follow_up'),
    path('patients/<str:patient_id>/records/add/', views.add_medical_record, name='add_medical_record'),
    path('follow-up/', views.DentalFollowUpListView.as_view(), name='followup_list'),
    path('follow-up/<int:pk>/complete/', views.complete_follow_up, name='complete_follow_up'),
    path('procedures/', views.procedure_list, name='procedure_list'),
]
