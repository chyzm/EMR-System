from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import (PatientListView, PatientDetailView, PatientCreateView,
                   StaffCreateView, PatientUpdateView, PatientDeleteView)
from core.views import select_clinic
from django.shortcuts import redirect


app_name = 'core'

urlpatterns = [
    
    path('select-clinic/', select_clinic, name='select_clinic'),
    
    # Authentication
    path('', lambda request: redirect('login'), name='home_redirect'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Role Management
    path('administration/manage-roles/', views.manage_user_roles, name='manage_roles'),
    path('administration/users/<int:user_id>/edit/', views.edit_user_role, name='edit_user_role'),

    # Patients
    path('patients/', PatientListView.as_view(), name='patient_list'),
    path('patients/<int:pk>/', PatientDetailView.as_view(), name='patient_detail'),
    path('patients/add/', PatientCreateView.as_view(), name='add_patient'),
    path('patients/<int:pk>/edit/', PatientUpdateView.as_view(), name='edit_patient'),
    path('patients/<int:pk>/delete/', PatientDeleteView.as_view(), name='delete_patient'),

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
    path('billing/create/patient/<int:patient_id>/', views.create_bill, name='create_bill_for_patient'),
    path('billing/create/appointment/<int:appointment_id>/', views.create_bill, name='create_bill_for_appointment'),
    path('billing/<int:pk>/', views.view_bill, name='view_bill'),
    path('billing/<int:pk>/edit/', views.edit_bill, name='edit_bill'),
    path('billing/<int:pk>/payment/', views.record_payment, name='record_payment'),
    path('billing/<int:pk>/receipt/', views.generate_receipt, name='generate_receipt'),
    path('billing/<int:pk>/delete/', views.delete_bill, name='delete_bill'),
    
    
    # AI assist
    path("api/ai-chat/", views.ai_chat, name="ai_chat"),
    
    
    
    path('select-clinic/', views.select_clinic, name='select_clinic'),
]