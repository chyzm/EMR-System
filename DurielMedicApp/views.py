from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.utils import timezone
from django.http import HttpResponse
from django.contrib.auth import get_user_model

from core.models import Patient, Clinic, Billing
from .models import (
    Appointment, Vitals, Admission, FollowUp,
    Prescription, MedicalRecord, Notification, NotificationRead
)
from core.views import PatientDetailView
from .forms import (
    VitalsForm, AppointmentForm, FollowUpForm,
    PrescriptionForm, MedicalRecordForm
)
from core.decorators import role_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.db.models import Q, Count
from datetime import date, timedelta
from .forms import VitalsForm, AdmissionForm, FollowUpForm
from django.urls import reverse, reverse_lazy  
from django.views.decorators.http import require_POST
from django.db.models.functions import Coalesce
from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Value
from django.db import transaction
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.utils.timezone import make_aware
from datetime import datetime, timedelta, time
from django.db.models import Count, Sum
from django.http import HttpResponse
import csv

from .models import Appointment  # adjust if needed
from .utils import admin_check  # or define your own admin_check function
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


User = get_user_model()


from core.models import Clinic


def staff_check(user):
    return user.is_authenticated and user.role in ['ADMIN', 'DOCTOR', 'NURSE', 'OPTOMETRIST', 'PHYSIOTHERAPIST', 'RECEPTIONIST']

def admin_check(user):
    return user.is_authenticated and user.role == 'ADMIN'

@login_required
def select_clinic(request):
    user_clinics = request.user.clinic.all()  # returns Clinic objects
    
    if request.method == 'POST':
        clinic_id = request.POST.get('clinic_id')
        clinic = Clinic.objects.filter(id=clinic_id, staff=request.user).first()
        if clinic:
            request.session['clinic_id'] = clinic.id
            request.session['clinic_type'] = clinic.clinic_type

            if clinic.clinic_type == 'GENERAL':
                return redirect('DurielMedicApp:dashboard')
            elif clinic.clinic_type == 'EYE':
                return redirect('eye_dashboard')
            elif clinic.clinic_type == 'DENTAL':
                return redirect('dental_dashboard')

    return render(request, 'select-clinic/select_clinic.html', {'clinics': user_clinics})



# --------------------
# Dashboard
# --------------------


@login_required
@user_passes_test(staff_check, login_url='login')
def dashboard(request):
    today = date.today()
    start_week = today - timedelta(days=today.weekday())
    end_week = start_week + timedelta(days=6)
    start_year = date(today.year, 1, 1)
    
    # Get selected clinic(s) from session
    clinic_filter = request.session.get('clinic_id')
    user_clinics = list(request.user.clinic.values_list('id', flat=True))
    
    # IGNORE CLINIC ASSIGNMENT FOR PATIENTS - Show all patients
    patients = Patient.objects.all()
    
    # Set clinic_filter for other queries that still need clinic filtering
    if clinic_filter:
        clinic_filter = [int(clinic_filter)]
    elif user_clinics:
        clinic_filter = user_clinics
    else:
        clinic_filter = []
    
    # Financial stats
    if clinic_filter:
        financial_stats = Billing.objects.filter(clinic__in=clinic_filter, status='PENDING').aggregate(
            total_count=Count('id'),
            total_amount=Coalesce(Sum('amount', output_field=DecimalField()), Value(0, output_field=DecimalField())),
            total_paid=Coalesce(Sum('paid_amount', output_field=DecimalField()), Value(0, output_field=DecimalField()))
        )
    else:
        financial_stats = Billing.objects.filter(status='PENDING').aggregate(
            total_count=Count('id'),
            total_amount=Coalesce(Sum('amount', output_field=DecimalField()), Value(0, output_field=DecimalField())),
            total_paid=Coalesce(Sum('paid_amount', output_field=DecimalField()), Value(0, output_field=DecimalField()))
        )
    
    stats = {
        'total_patients': patients.count(),
        'new_patients_this_week': patients.filter(created_at__date__range=[start_week, today]).count(),
        'new_patients_this_year': patients.filter(created_at__date__gte=start_year).count(),
        'today_appointments': Appointment.objects.filter(clinic__in=clinic_filter, date=today).count() if clinic_filter else Appointment.objects.filter(date=today).count(),
        'completed_appointments_today': Appointment.objects.filter(clinic__in=clinic_filter, date=today, status='COMPLETED').count() if clinic_filter else Appointment.objects.filter(date=today, status='COMPLETED').count(),
        'week_appointments': Appointment.objects.filter(clinic__in=clinic_filter, date__range=[start_week, end_week]).count() if clinic_filter else Appointment.objects.filter(date__range=[start_week, end_week]).count(),
        'pending_prescriptions': Prescription.objects.filter(is_active=True).count(),
        'new_prescriptions_this_week': Prescription.objects.filter(date_prescribed__range=[start_week, today]).count(),
        'pending_bills': financial_stats['total_count'],
        'total_pending_amount': financial_stats['total_amount'],
        'outstanding_balance': financial_stats['total_amount'] - financial_stats['total_paid'],
    }
    
    # Get today's appointments (most recent first)
    user_appointments = Appointment.objects.filter(
        clinic__in=clinic_filter,
        date=today
    ).order_by('-start_time') if clinic_filter else Appointment.objects.filter(date=today).order_by('-start_time')
    
    # Paginate appointments
    page = request.GET.get('page', 1)
    paginator = Paginator(user_appointments, 3)  # 3 appointments per page
    
    try:
        user_appointments_page = paginator.page(page)
    except PageNotAnInteger:
        user_appointments_page = paginator.page(1)
    except EmptyPage:
        user_appointments_page = paginator.page(paginator.num_pages)
    
    # Get recent patients (last 5 registered)
    recent_patients = Patient.objects.order_by('-created_at')[:5]
    
    # Get unread notifications
    read_global_ids = NotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
    notifications = Notification.objects.filter(
        Q(user=request.user, is_read=False) | Q(user__isnull=True)
    ).exclude(id__in=read_global_ids).order_by('-created_at')[:5]
    
    context = {
        'stats': stats,
        'user_appointments': user_appointments_page,
        'recent_patients': recent_patients,  # Now properly defined
        'notifications': notifications,
        'today': today,
    }
    
    return render(request, 'dashboard.html', context)





# @login_required
# @user_passes_test(staff_check, login_url='login')
# def dashboard(request):
#     today = date.today()
#     start_week = today - timedelta(days=today.weekday())
#     end_week = start_week + timedelta(days=6)
#     start_year = date(today.year, 1, 1)
    
#     # Get selected clinic(s) from session
#     clinic_filter = request.session.get('clinic_id')
#     print(f"Raw clinic_id from session: {clinic_filter}")
    
#     # Get user's clinics for other filtering (appointments, prescriptions, billing)
#     user_clinics = list(request.user.clinic.values_list('id', flat=True))
#     print(f"User's clinic IDs: {user_clinics}")
    
#     # IGNORE CLINIC ASSIGNMENT FOR PATIENTS - Show all patients
#     patients = Patient.objects.all()
#     print(f"Total patients (ignoring clinic filter): {patients.count()}")
    
#     # Set clinic_filter for other queries that still need clinic filtering
#     if clinic_filter:
#         clinic_filter = [int(clinic_filter)]
#     elif user_clinics:
#         clinic_filter = user_clinics
#     else:
#         clinic_filter = []
    
#     print(f"Clinic filter for other queries: {clinic_filter}")
    
#     # Financial stats
#     if clinic_filter:
#         financial_stats = Billing.objects.filter(clinic__in=clinic_filter, status='PENDING').aggregate(
#             total_count=Count('id'),
#             total_amount=Coalesce(
#                 Sum('amount', output_field=DecimalField()),
#                 Value(0, output_field=DecimalField())
#             ),
#             total_paid=Coalesce(
#                 Sum('paid_amount', output_field=DecimalField()),
#                 Value(0, output_field=DecimalField())
#             )
#         )
#     else:
#         # If no clinic filter, get all billing stats
#         financial_stats = Billing.objects.filter(status='PENDING').aggregate(
#             total_count=Count('id'),
#             total_amount=Coalesce(
#                 Sum('amount', output_field=DecimalField()),
#                 Value(0, output_field=DecimalField())
#             ),
#             total_paid=Coalesce(
#                 Sum('paid_amount', output_field=DecimalField()),
#                 Value(0, output_field=DecimalField())
#             )
#         )
    
#     # Debug: Print values to check what's being calculated
#     final_patient_count = patients.count()
#     print(f"Final patient count (all patients): {final_patient_count}")
#     print(f"Clinic filter for other queries: {clinic_filter}")
    
#     stats = {
#         'total_patients': final_patient_count,
#         'new_patients_this_week': patients.filter(
#             created_at__date__range=[start_week, today]
#         ).count(),
#         'new_patients_this_year': patients.filter(
#             created_at__date__gte=start_year
#         ).count(),
        
#         # Appointments - still filtered by clinic
#         'today_appointments': Appointment.objects.filter(clinic__in=clinic_filter, date=today).count() if clinic_filter else Appointment.objects.filter(date=today).count(),
#         'completed_appointments_today': Appointment.objects.filter(
#             clinic__in=clinic_filter, date=today, status='COMPLETED'
#         ).count() if clinic_filter else Appointment.objects.filter(date=today, status='COMPLETED').count(),
#         'week_appointments': Appointment.objects.filter(
#             clinic__in=clinic_filter,
#             date__range=[start_week, end_week]
#         ).count() if clinic_filter else Appointment.objects.filter(date__range=[start_week, end_week]).count(),
        
#         # Prescriptions - show all prescriptions (ignore clinic filter)
#         'pending_prescriptions': Prescription.objects.filter(is_active=True).count(),
#         'new_prescriptions_this_week': Prescription.objects.filter(date_prescribed__range=[start_week, today]).count(),
        
#         # Billing - still filtered by clinic if available
#         'pending_bills': financial_stats['total_count'],
#         'total_pending_amount': financial_stats['total_amount'],
#         'outstanding_balance': financial_stats['total_amount'] - financial_stats['total_paid'],
#     }
    
#     print(f"Stats total_patients value: {stats['total_patients']}")
    
#     # Change the ordering to show most recent appointments first
#     user_appointments = Appointment.objects.filter(
#         clinic__in=clinic_filter,
#         date=today
#     ).order_by('-start_time')[:5] if clinic_filter else Appointment.objects.filter(
#         date=today
#     ).order_by('-start_time')[:5]
    
#     # Paginate today's appointments (now ordered newest first)
#     page = request.GET.get('page', 1)
#     paginator = Paginator(user_appointments, 5)  # Show 5 appointments per page
    
#     try:
#         user_appointments_page = paginator.page(page)
#     except PageNotAnInteger:
#         user_appointments_page = paginator.page(1)
#     except EmptyPage:
#         user_appointments_page = paginator.page(paginator.num_pages)
        
    
#     read_global_ids = NotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
#     notifications = Notification.objects.filter(
#         Q(user=request.user, is_read=False) | Q(user__isnull=True)
#     ).exclude(id__in=read_global_ids).order_by('-created_at')[:5]
    
#     context = {
#         'stats': stats,
#         'user_appointments': user_appointments,
#         'recent_patients': recent_patients,
#         'notifications': notifications,
#         'today': today,
#     }
    
#     return render(request, 'dashboard.html', context)






# --------------------
# Appointments
# --------------------
# 


class AppointmentListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Appointment
    template_name = 'appointments/appointment_list.html'
    context_object_name = 'appointments'
    paginate_by = 10
    
    def test_func(self):
        return self.request.user.is_authenticated and staff_check(self.request.user)
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by date if provided
        date_filter = self.request.GET.get('date', '')
        if date_filter:
            queryset = queryset.filter(date=date_filter)
        
        # For non-admin staff, only show their appointments or patients they created
        if not self.request.user.role == 'ADMIN':
            queryset = queryset.filter(
                Q(provider=self.request.user) | 
                Q(patient__created_by=self.request.user)
            )
        
        return queryset.order_by('date', 'start_time')


# @login_required
# def appointment_create(request):
#     if request.method == 'POST':
#         form = AppointmentForm(request.POST)
#         if form.is_valid():
#             appt = form.save(commit=False)
#             appt.provider = request.user
#             appt.save()
#             messages.success(request, "Appointment scheduled successfully.")
#             return redirect('DurielMedicApp:appointment_list')
#     else:
#         form = AppointmentForm()
#     return render(request, 'DurielMedicApp/appointment_form.html', {'form': form})


class AppointmentCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Appointment
    form_class = AppointmentForm
    template_name = 'appointments/appointment_form.html'
    success_url = reverse_lazy('appointment_list')
    
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role in ['ADMIN', 'DOCTOR', 'RECEPTIONIST']
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['initial'] = {'provider': self.request.user}
        return kwargs
    
    def form_valid(self, form):
        
        form.instance.provider = self.request.user  # 👈 THIS is crucial
        print("Saving appointment for:", form.cleaned_data.get('patient'))

        appointment = form.save(commit=False)
        appointment.save()

        messages.success(self.request, 'Appointment scheduled successfully!')
        return redirect(self.success_url)
    
    

@login_required
def appointment_detail(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    return render(request, 'DurielMedicApp/appointment_detail.html', {'appointment': appointment})


# --------------------
# Vitals & Consultation
# --------------------
@login_required 
@role_required('NURSE', 'DOCTOR')
def record_vitals(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    appointment = patient.appointments.filter(status='SCHEDULED').order_by('-date', '-start_time').first()

    if not appointment:
        messages.error(request, "No active appointment found for this patient.")
        return redirect('core:patient_detail', pk=patient_id)

    if request.method == 'POST':
        form = VitalsForm(request.POST)
        if form.is_valid():
            vitals = form.save(commit=False)
            vitals.appointment = appointment
            vitals.save()

            # Update patient status
            patient.status = 'VITALS_TAKEN'
            patient.save()

            messages.success(request, "Vitals recorded successfully!")
            return redirect('core:patient_detail', pk=patient_id)
    else:
        form = VitalsForm(initial={'appointment': appointment})

    return render(request, 'vitals/record_vitals.html', {
        'form': form,
        'patient': patient,
        'appointment': appointment
    })


# --------------------
# Admissions
# --------------------
@login_required
@role_required('DOCTOR', 'NURSE')
def admit_patient(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    if request.method == 'POST':
        ward = request.POST.get('ward')
        reason = request.POST.get('reason')
        Admission.objects.create(patient=patient, ward=ward, reason=reason)
        messages.success(request, "Patient admitted successfully.")
        return redirect('core:patient_detail', pk=patient_id)
    return render(request, 'DurielMedicApp/admit_patient.html', {'patient': patient})


@login_required
def discharge_patient(request, admission_id):
    admission = get_object_or_404(Admission, pk=admission_id)
    admission.discharged = True
    admission.save()
    messages.success(request, "Patient discharged successfully.")
    return redirect('core:patient_detail', pk=admission.patient.pk)


# --------------------
# Follow-ups
# --------------------
@login_required
def create_follow_up(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    if request.method == 'POST':
        form = FollowUpForm(request.POST)
        if form.is_valid():
            follow_up = form.save(commit=False)
            follow_up.patient = patient
            follow_up.created_by = request.user
            follow_up.save()
            messages.success(request, "Follow-up created successfully.")
            return redirect('core:patient_detail', pk=patient_id)
    else:
        form = FollowUpForm()
    return render(request, 'DurielMedicApp/followup_form.html', {'form': form, 'patient': patient})


# --------------------
# Prescriptions
# --------------------
# @login_required
# def create_prescription(request, patient_id):
#     patient = get_object_or_404(Patient, pk=patient_id)
#     if request.method == 'POST':
#         form = PrescriptionForm(request.POST)
#         if form.is_valid():
#             prescription = form.save(commit=False)
#             prescription.patient = patient
#             prescription.prescribed_by = request.user
#             prescription.save()
#             messages.success(request, "Prescription created successfully.")
#             return redirect('core:patient_detail', pk=patient_id)
#     else:
#         form = PrescriptionForm()
#     return render(request, 'DurielMedicApp/prescription_form.html', {'form': form, 'patient': patient})


# --------------------
# Medical Records
# --------------------
@login_required
@role_required('ADMIN', 'DOCTOR', 'NURSE')
def add_medical_record(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    if request.method == 'POST':
        form = MedicalRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.patient = patient
            record.created_by = request.user
            record.save()
            messages.success(request, 'Medical record added successfully!')
            return redirect('core:patient_detail', pk=patient.pk)
    else:
        form = MedicalRecordForm()
    
    return render(request, 'medical_records/add_medical_record.html', {
        'form': form,
        'patient': patient
    })
    
    
@login_required
@role_required('ADMIN', 'DOCTOR', 'NURSE')
def edit_medical_record(request, record_id):
    record = get_object_or_404(MedicalRecord, pk=record_id)
    if request.method == 'POST':
        form = MedicalRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, 'Medical record updated successfully!')
            return redirect('core:patient_detail', pk=record.patient.pk)
    else:
        form = MedicalRecordForm(instance=record)
    
    return render(request, 'medical_records/edit_medical_record.html', {
        'form': form,
        'record': record
    })

@login_required
@role_required('ADMIN', 'DOCTOR')
def delete_medical_record(request, record_id):
    record = get_object_or_404(MedicalRecord, pk=record_id)
    patient_id = record.patient.pk
    record.delete()
    messages.success(request, 'Medical record deleted successfully!')
    return redirect('core:patient_detail', pk=patient_id)



def patient_search_api(request):
    query = request.GET.get('q', '')
    results = Patient.objects.filter(full_name__icontains=query)
    data = [{'id': p.id, 'name': p.full_name} for p in results]
    return JsonResponse({'results': data})



# --------------------
# Notifications
# --------------------
    
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

@login_required
@role_required('ADMIN', 'DOCTOR', 'NURSE', 'OPTOMETRIST', 'PHYSIOTHERAPIST', 'RECEPTIONIST')  # or whatever roles you need
def mark_notification_read(request, pk):  # Make sure to include the pk parameter
    notification = get_object_or_404(Notification, pk=pk)
    
    # Mark as read for personal notifications
    if notification.user == request.user:
        notification.is_read = True
        notification.save()
    # Mark as read for global notifications (user=None)
    elif notification.user is None:
        NotificationRead.objects.get_or_create(
            user=request.user,
            notification=notification
        )
    
    return redirect(request.META.get('HTTP_REFERER', 'DurielMedicApp:dashboard'))



# @login_required
# @csrf_exempt
# def mark_notification_read(request):
#     # Mark personal notifications
#     Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)

#     # Mark global notifications as read per user
#     unread_globals = Notification.objects.filter(user__isnull=True).exclude(
#         id__in=NotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
#     )
#     NotificationRead.objects.bulk_create([
#         NotificationRead(user=request.user, notification=n) for n in unread_globals
#     ], ignore_conflicts=True)

#     return JsonResponse({'status': 'success'})


# Appointment Views
class AppointmentListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Appointment
    template_name = 'appointments/appointment_list.html'
    context_object_name = 'appointments'
    paginate_by = 10
    
    def test_func(self):
        return self.request.user.is_authenticated and staff_check(self.request.user)
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by date if provided
        date_filter = self.request.GET.get('date', '')
        if date_filter:
            queryset = queryset.filter(date=date_filter)
        
        # For non-admin staff, only show their appointments or patients they created
        if not self.request.user.role == 'ADMIN':
            queryset = queryset.filter(
                Q(provider=self.request.user) | 
                Q(patient__created_by=self.request.user)
            )
        
        return queryset.order_by('date', 'start_time')

class AppointmentCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Appointment
    form_class = AppointmentForm
    template_name = 'appointments/appointment_form.html'
    success_url = reverse_lazy('appointment_list')
    
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role in ['ADMIN', 'DOCTOR', 'RECEPTIONIST']
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['initial'] = {'provider': self.request.user}
        return kwargs
    
    def form_valid(self, form):
        
        form.instance.provider = self.request.user  # 👈 THIS is crucial
        print("Saving appointment for:", form.cleaned_data.get('patient'))

        appointment = form.save(commit=False)
        appointment.save()

        messages.success(self.request, 'Appointment scheduled successfully!')
        return redirect(self.success_url)
    
    
    



@require_POST
@login_required
def mark_appointment_completed(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    appointment.status = 'COMPLETED'
    appointment.save()
    
    # Check if bill already exists
    if not hasattr(appointment, 'bill'):
        messages.info(request, 'Appointment marked as completed. Would you like to create a bill?')
        
        return redirect('DurielMedicApp:create_bill_for_appointment', appointment_id=appointment.pk)
    
    messages.success(request, 'Appointment marked as completed.')
    return redirect('DurielMedicApp:appointment_list')


@require_POST
@login_required
def mark_appointment_cancelled(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    appointment.status = 'CANCELLED'
    appointment.save()
    messages.warning(request, 'Appointment marked as cancelled.')
    return redirect('DurielMedicApp:appointment_list')


class FollowUpListView(LoginRequiredMixin, ListView):
    model = FollowUp
    template_name = 'follow_up/followup_list.html'
    context_object_name = 'followups'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if not user.is_superuser:
            role = getattr(user, 'role', None)

            if role == 'DOCTOR':
                queryset = queryset.filter(created_by=user)
            elif role == 'NURSE':
                # Change this logic based on your actual nurse-followup link
                # For now, allow nurse to see all follow-ups
                queryset = queryset  # or .none() if nurses should not see any

        return queryset.order_by('scheduled_date', 'scheduled_time')


class FollowUpCreateView(LoginRequiredMixin, CreateView):
    model = FollowUp
    template_name = 'follow_up/schedule_follow_up.html'
    fields = ['patient', 'reason', 'scheduled_date', 'scheduled_time', 'notes']
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

class FollowUpUpdateView(LoginRequiredMixin, UpdateView):
    model = FollowUp
    template_name = 'followup_form.html'
    fields = ['reason', 'scheduled_date', 'scheduled_time', 'notes', 'completed']

    
    

@login_required
@role_required('DOCTOR', 'NURSE')
def admit_patient(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    
    # Allow admission from multiple states
    if patient.status not in ['VITALS_TAKEN', 'CONSULTATION_COMPLETE']:
        messages.error(request, "Patient must have vitals taken or consultation completed first")
        return redirect('core:patient_detail', pk=patient_id)
    
    if request.method == 'POST':
        form = AdmissionForm(request.POST)
        if form.is_valid():
            admission = form.save(commit=False)
            admission.patient = patient
            admission.save()
            
            patient.status = 'ADMITTED'
            patient.save()
            
            messages.success(request, "Patient admitted successfully!")
            return redirect('core:patient_detail', pk=patient_id)
    else:
        form = AdmissionForm(initial={'patient': patient})
    
    return render(request, 'admission/admit_patient.html', {
        'form': form,
        'patient': patient,
        'from_consultation': patient.status == 'CONSULTATION_COMPLETE'
    })
    
    
    

@login_required
@role_required('DOCTOR')
def mark_ready_for_doctor(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    
    if patient.status != 'ADMITTED':
        messages.error(request, "Patient must be admitted before seeing doctor")
        return redirect('core:patient_detail', pk=patient_id)
    
    patient.status = 'SEEN_BY_DOCTOR'
    patient.save()
    
    messages.success(request, "Patient is now with doctor")
    return redirect('core:patient_detail', pk=patient_id)



@login_required
@role_required('DOCTOR', 'NURSE')
def discharge_patient(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    admission = Admission.objects.filter(patient=patient, discharged=False).first()
    
    if not admission:
        messages.error(request, "No active admission found for this patient")
        return redirect('core:patient_detail', pk=patient_id)
    
    admission.discharged = True
    admission.save()
    
    # Reset patient status
    patient.status = 'REGISTERED'
    patient.save()
    
    messages.success(request, "Patient discharged successfully")
    return redirect('core:patient_detail', pk=patient_id)




@login_required
def add_prescription(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id)

    if request.method == 'POST':
        medication = request.POST.get('medication')
        dosage = request.POST.get('dosage')
        instructions = request.POST.get('instructions')

        # Validation (optional)
        if not medication or not dosage:
            messages.error(request, "Please fill in all required fields.")
        else:
            Prescription.objects.create(
                patient=patient,
                medication=medication,
                dosage=dosage,
                instructions=instructions,
                prescribed_by=request.user  
            )
            messages.success(request, "Prescription saved successfully.")
            return redirect('core:patient_detail', pk=patient.patient_id)
        Notification.objects.create(
            user=prescription.patient.created_by,
            message=f"New prescription for {prescription.patient.full_name}",
            link=reverse('core:patient_detail', kwargs={'pk': prescription.patient.pk})
        )

    return render(request, 'prescription/add_prescription.html', {'patient': patient})




@login_required
def edit_prescription(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk)
    patient = prescription.patient

    if request.method == 'POST':
        prescription.medication = request.POST.get('medication')
        prescription.dosage = request.POST.get('dosage')
        prescription.instructions = request.POST.get('instructions')
        prescription.save()
        return redirect('DurielMedicApp:patient_detail', pk=patient.patient_id)

    return render(request, 'prescription/edit_prescription.html', {'prescription': prescription, 'patient': patient})

@login_required
def prescription_list(request):
    query = request.GET.get('q', '')

    # Fetch prescriptions with related patient and doctor, no values() or annotate()
    prescriptions = Prescription.objects.select_related('patient', 'prescribed_by')

    if query:
        prescriptions = prescriptions.filter(
            Q(patient__full_name__icontains=query) |
            Q(prescribed_by__first_name__icontains=query) |
            Q(prescribed_by__last_name__icontains=query) |
            Q(medication__icontains=query) |
            Q(date_prescribed__icontains=query)
        )

    context = {
        'prescriptions': prescriptions.order_by('-date_prescribed'),
        'query': query,
    }
    return render(request, 'prescription/prescription_list.html', context)


@login_required
def deactivate_prescription(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk)
    patient = prescription.patient

    if request.method == 'POST':
        prescription.is_active = False
        prescription.save()
        return redirect('core:patient_detail', pk=patient.patient_id)

    return render(request, 'prescription/deactivate_prescription.html', {
        'prescription': prescription,
        'patient': patient
    })
    
    
    
    
@login_required
@role_required('ADMIN', 'DOCTOR', 'NURSE')
def edit_medical_record(request, record_id):
    record = get_object_or_404(MedicalRecord, pk=record_id)
    if request.method == 'POST':
        form = MedicalRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, 'Medical record updated successfully!')
            return redirect('core:patient_detail', pk=record.patient.pk)
    else:
        form = MedicalRecordForm(instance=record)
    
    return render(request, 'medical_records/edit_medical_record.html', {
        'form': form,
        'record': record
    })

@login_required
@role_required('ADMIN', 'DOCTOR')
def delete_medical_record(request, record_id):
    record = get_object_or_404(MedicalRecord, pk=record_id)
    patient_id = record.patient.pk
    record.delete()
    messages.success(request, 'Medical record deleted successfully!')
    return redirect('core:patient_detail', pk=patient_id)



def patient_search_api(request):
    query = request.GET.get('q', '')
    results = Patient.objects.filter(full_name__icontains=query)
    data = [{'id': p.id, 'name': p.full_name} for p in results]
    return JsonResponse({'results': data})




# Appointment List View
# 1. List all appointments (for staff/admin)
@login_required
def appointment_list(request):
    appointments = Appointment.objects.all().order_by('-date')
    return render(request, 'appointments/appointment_list.html', {'appointments': appointments})


# 2. Create new appointment
@login_required
def appointment_create(request):
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Appointment scheduled successfully.')
            return redirect('appointment_list')
    else:
        form = AppointmentForm()
    
    return render(request, 'appointments/appointment_form.html', {'form': form})


# 3. Update appointment
@login_required
def appointment_update(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    
    form = AppointmentForm(request.POST or None, instance=appointment)
    if form.is_valid():
        form.save()
        messages.success(request, 'Appointment updated successfully.')
        return redirect('DurielMedicApp:appointment_list')
    
    return render(request, 'appointments/appointment_form.html', {'form': form})


# 4. Delete appointment
@login_required
def appointment_delete(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    
    if request.method == 'POST':
        appointment.delete()
        messages.success(request, 'Appointment deleted successfully.')
        return redirect('DurielMedicApp:appointment_list')
    
    return render(request, 'appointments/appointment_confirm_delete.html', {'appointment': appointment})


# 5. Check appointment availability via API
@login_required
def check_appointment_availability(request):
    provider_id = request.GET.get('provider')
    date = request.GET.get('date')
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    
    if not all([provider_id, date, start_time, end_time]):
        return JsonResponse({'available': False, 'error': 'Missing required parameters'}, status=400)
    
    try:
        overlapping = Appointment.objects.filter(
            provider_id=provider_id,
            date=date,
            start_time__lt=end_time,
            end_time__gt=start_time
        )
        available = not overlapping.exists()
        return JsonResponse({'available': available})
    except Exception as e:
        return JsonResponse({'available': False, 'error': str(e)}, status=500)


@login_required
def add_appointment(request):
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.provider = request.user

            if request.user.clinic is None:
                messages.error(request, "Your account is not assigned to a clinic. Please contact the admin.")
                return redirect('DurielMedicApp:add_appointment')

            # appointment.clinic = request.user.clinic
            appointment.clinic = request.user.clinic.first()
            appointment.status = 'SCHEDULED'
            appointment.save()

            # ✅ Reset patient status to REGISTERED for fresh visit
            appointment.patient.status = 'REGISTERED'
            appointment.patient.save()

            # Notify all active users
            from django.contrib.auth import get_user_model
            User = get_user_model()
            staff_users = User.objects.filter(is_active=True)
            for user in staff_users:
                Notification.objects.create(
                    user=user,
                    message=f"New appointment with {appointment.patient.full_name} on {appointment.date}",
                    link=reverse('DurielMedicApp:appointment_list')
                )

            messages.success(request, 'Appointment scheduled successfully!')
            return redirect('DurielMedicApp:appointment_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = AppointmentForm(initial={'provider': request.user})

    return render(request, 'appointments/add_appointment.html', {
        'form': form,
        'title': 'Add New Appointment',
    })





# Notification Views


def check_birthdays():
    today = date.today()
    patients = Patient.objects.filter(
        date_of_birth__month=today.month,
        date_of_birth__day=today.day
    )
    
    for patient in patients:
        # Create notification for staff
        Notification.objects.create(
            user=patient.created_by,
            message=f"Today is {patient.full_name}'s birthday!",
            link=reverse('DurielMedicApp:patient_detail', kwargs={'pk': patient.pk})
        )
        
        # Send email if email exists
        if patient.email:
            send_mail(
                'Happy Birthday!',
                f'Dear {patient.full_name},\n\nHappy Birthday from DurielMedic+!',
                settings.DEFAULT_FROM_EMAIL,
                [patient.email],
                fail_silently=True
            )
        


# from django.views.decorators.csrf import csrf_exempt

# @login_required
# @csrf_exempt
# def mark_notification_read(request):
#     # Mark personal notifications
#     Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)

#     # Mark global notifications as read per user
#     unread_globals = Notification.objects.filter(user__isnull=True).exclude(
#         id__in=NotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
#     )
#     NotificationRead.objects.bulk_create([
#         NotificationRead(user=request.user, notification=n) for n in unread_globals
#     ], ignore_conflicts=True)

#     return JsonResponse({'status': 'success'})



@login_required
def clear_notifications(request):
    # Delete user-specific notifications
    request.user.notifications.all().delete()

    # Mark global as read (don't delete them)
    unread_globals = Notification.objects.filter(user__isnull=True).exclude(
        id__in=NotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
    )
    NotificationRead.objects.bulk_create([
        NotificationRead(user=request.user, notification=n) for n in unread_globals
    ], ignore_conflicts=True)

    messages.success(request, "Notifications cleared")
    return redirect(request.META.get('HTTP_REFERER', 'DurielMedicApp:dashboard'))



@login_required
@role_required('DOCTOR')
def begin_consultation(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    
    if patient.status != 'VITALS_TAKEN':
        messages.error(request, "Patient vitals must be taken before consultation")
        return redirect('core:patient_detail', pk=patient_id)
    
    patient.status = 'IN_CONSULTATION'
    patient.save()

    # ✅ Send notification to all active users
    User = get_user_model()
    users = User.objects.filter(is_active=True)

    for user in users:
        Notification.objects.create(
            user=user,
            message=f"Consultation started for patient {patient.full_name}",
            link=reverse('core:patient_detail', kwargs={'pk': patient_id})
        )

    messages.success(request, "Consultation started")
    return redirect('core:patient_detail', pk=patient_id)





from django.contrib.auth import get_user_model

@login_required
@role_required('DOCTOR')
def complete_consultation(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)

    if patient.status != 'IN_CONSULTATION':
        messages.error(request, "Patient must be in consultation first")
        return redirect('core:patient_detail', pk=patient_id)

    # Get the clinic from the session or patient
    clinic_id = request.session.get('clinic_id')
    if not clinic_id and patient.clinic:
        clinic_id = patient.clinic.id
    
    if not clinic_id:
        messages.error(request, "No clinic associated with this patient or session")
        return redirect('core:patient_detail', pk=patient_id)

    consultation_fee = Decimal('10000.00')  # Example amount

    try:
        with transaction.atomic():
            patient.status = 'CONSULTATION_COMPLETE'
            patient.save()

            bill = Billing.objects.create(
                patient=patient,
                amount=consultation_fee,
                description=f"Consultation fee - {date.today()}",
                service_date=date.today(),
                due_date=date.today() + timedelta(days=14),
                created_by=request.user,
                clinic_id=clinic_id  # Use clinic_id directly
            )

            # Send notifications
            User = get_user_model()
            for user in User.objects.filter(is_active=True):
                Notification.objects.create(
                    user=user,
                    message=f"New bill for {patient.full_name} - ₦{consultation_fee:,.2f}",
                    link=reverse('core:view_bill', kwargs={'pk': bill.pk})
                )

            messages.success(request, "Consultation completed and bill created")
    except Exception as e:
        messages.error(request, f"Error completing consultation: {str(e)}")
    
    return redirect('core:patient_detail', pk=patient_id)


@login_required
@role_required('DOCTOR')
def schedule_follow_up(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    
    if patient.status not in ['IN_CONSULTATION', 'CONSULTATION_COMPLETE']:
        messages.error(request, "Patient must complete consultation first")
        return redirect('core:patient_detail', pk=patient_id)
    
    if request.method == 'POST':
        form = FollowUpForm(request.POST)
        if form.is_valid():
            follow_up = form.save(commit=False)
            follow_up.patient = patient
            follow_up.created_by = request.user
            follow_up.save()
            
            patient.status = 'FOLLOW_UP'
            patient.save()
            
            messages.success(request, "Follow-up scheduled successfully!")
            return redirect('core:patient_detail', pk=patient_id)
    else:
        form = FollowUpForm()
    
    return render(request, 'follow_up/schedule_follow_up.html', {
        'form': form,
        'patient': patient,
        'from_consultation': patient.status == 'IN_CONSULTATION'
    })
    
    
@login_required
def complete_follow_up(request, pk):
    follow_up = get_object_or_404(FollowUp, pk=pk)
    patient = follow_up.patient  # Get the patient from the follow-up
    
    if not follow_up.completed:
        follow_up.completed = True
        follow_up.save()
        
        # Update patient status if this was their last pending follow-up
        if not patient.follow_ups.filter(completed=False).exists():
            patient.status = 'FOLLOW_UP_COMPLETE'
            patient.save()
        
        messages.success(request, "Follow-up marked as complete.")
    else:
        messages.warning(request, "This follow-up was already completed.")
    
    return redirect('DurielMedicApp:patient_detail', pk=patient.pk)





@login_required
@user_passes_test(admin_check, login_url='login')
def generate_report(request):
    # Default date range: last 30 days
    end_date = timezone.now()
    start_date = end_date - timedelta(days=30)

    if request.method == 'POST':
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        report_type = request.POST.get('report_type')

        if start_date_str and end_date_str:
            start_date = make_aware(datetime.combine(datetime.strptime(start_date_str, '%Y-%m-%d'), time.min))
            end_date = make_aware(datetime.combine(datetime.strptime(end_date_str, '%Y-%m-%d'), time.max))

        # Route to correct report
        if report_type == 'appointments':
            return generate_appointment_report(start_date, end_date)
        elif report_type == 'patients':
            return generate_patient_report(start_date, end_date)
        elif report_type == 'financial':
            return generate_financial_report(start_date, end_date)

    # Dashboard Summary Stats
    appointment_stats = Appointment.objects.filter(
        date__range=[start_date.date(), end_date.date()]
    ).values('status').annotate(count=Count('id'))

    patient_stats = Patient.objects.filter(
        created_at__range=[start_date, end_date]
    ).aggregate(total=Count('patient_id'))

    financial_stats = Billing.objects.filter(
        service_date__range=[start_date.date(), end_date.date()]
    ).aggregate(
        total_amount=Sum('amount'),
        total_paid=Sum('paid_amount')
    )

    context = {
        'start_date': start_date.date(),
        'end_date': end_date.date(),
        'appointment_stats': appointment_stats,
        'patient_stats': patient_stats,
        'financial_stats': financial_stats,
    }

    return render(request, 'reports/generate_report.html', context)


def generate_appointment_report(start_date, end_date):
    appointments = Appointment.objects.filter(
        date__range=[start_date.date(), end_date.date()]
    ).select_related('patient', 'provider').order_by('date', 'start_time')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="appointments_report_{start_date.date()}_to_{end_date.date()}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Date', 'Time', 'Patient', 'Provider', 'Status', 'Reason'])

    for appt in appointments:
        writer.writerow([
            appt.date,
            f"{appt.start_time} - {appt.end_time}",
            appt.patient.full_name,
            appt.provider.get_full_name(),
            appt.get_status_display(),
            appt.reason
        ])

    return response


def generate_patient_report(start_date, end_date):
    patients = Patient.objects.filter(
        created_at__range=[start_date, end_date]
    ).order_by('created_at')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="patients_report_{start_date.date()}_to_{end_date.date()}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Patient ID', 'Name', 'Gender', 'Date of Birth', 'Contact', 'Registered On'])

    for patient in patients:
        writer.writerow([
            patient.patient_id,
            patient.full_name,
            patient.get_gender_display(),
            patient.date_of_birth,
            patient.contact,
            patient.created_at.strftime('%Y-%m-%d %H:%M')
        ])

    return response


def generate_financial_report(start_date, end_date):
    try:
        bills = Billing.objects.filter(
            service_date__range=[start_date.date(), end_date.date()]
        ).select_related('patient').order_by('service_date')

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="financial_report_'
            f'{start_date.date()}_to_{end_date.date()}.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(['Bill Date', 'Patient', 'Amount', 'Paid', 'Balance', 'Status', 'Description'])

        for bill in bills:
            amount = bill.amount or 0
            paid = bill.paid_amount or 0
            balance = amount - paid

            writer.writerow([
                bill.service_date.strftime('%Y-%m-%d') if bill.service_date else '',
                bill.patient.full_name if bill.patient else 'Unknown Patient',
                amount,
                paid,
                balance,
                bill.get_status_display() if bill.status else '',
                bill.description or ''
            ])

        return response

    except Exception as e:
        print(f"Error generating financial report: {str(e)}")
        return HttpResponse(
            "An error occurred while generating the report. Please try again later.",
            content_type='text/plain',
            status=500
        )