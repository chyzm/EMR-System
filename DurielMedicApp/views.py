from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import get_user_model

from core.models import Patient, Clinic, Billing
from .models import (
    Appointment, Vitals, Admission, FollowUp,
    Prescription, MedicalRecord, Notification, NotificationRead
)
from core.views import PatientDetailView
from .forms import (
    VitalsForm, AppointmentForm, FollowUpForm,
    MedicalRecordForm
)
from core.forms import PrescriptionForm
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
from django.core.mail import send_mail
from core.utils import log_action
from core.models import Clinic

User = get_user_model()





def staff_check(user):
    return user.is_authenticated and user.role in ['ADMIN', 'DOCTOR', 'NURSE', 'OPTOMETRIST', 'PHYSIOTHERAPIST', 'RECEPTIONIST']

def admin_check(user):
    return user.is_authenticated and user.role == 'ADMIN'




@login_required
@user_passes_test(staff_check, login_url='login')
def dashboard(request):
    today = date.today()
    start_week = today - timedelta(days=today.weekday())
    end_week = start_week + timedelta(days=6)
    start_year = date(today.year, 1, 1)

    # Get the clinic ID from the session or the user's primary clinic
    clinic_id = request.session.get('clinic_id')
    if not clinic_id and hasattr(request.user, 'primary_clinic') and request.user.primary_clinic:
        clinic_id = request.user.primary_clinic.id
        request.session['clinic_id'] = clinic_id

    # --- Birthday notifications ---
    check_birthdays(clinic_id)  # <-- Ensure this runs every dashboard load

    # Filter all queries by the clinic ID
    patients = Patient.objects.all()
    if clinic_id:
        patients = patients.filter(clinic_id=clinic_id)

    # Financial stats
    financial_stats = Billing.objects.filter(clinic_id=clinic_id, status='PENDING').aggregate(
        total_count=Count('id'),
        total_amount=Coalesce(Sum('amount', output_field=DecimalField()), Value(0, output_field=DecimalField())),
        total_paid=Coalesce(Sum('paid_amount', output_field=DecimalField()), Value(0, output_field=DecimalField()))
    )

    stats = {
        'total_patients': patients.count(),
        'new_patients_this_week': patients.filter(created_at__date__range=[start_week, today]).count(),
        'new_patients_this_year': patients.filter(created_at__date__gte=start_year).count(),
        'today_appointments': Appointment.objects.filter(clinic_id=clinic_id, date=today).count(),
        'completed_appointments_today': Appointment.objects.filter(clinic_id=clinic_id, date=today, status='COMPLETED').count(),
        'week_appointments': Appointment.objects.filter(clinic_id=clinic_id, date__range=[start_week, end_week]).count(),
        'pending_prescriptions': Prescription.objects.filter(patient__clinic_id=clinic_id, is_active=True).count(),
        'new_prescriptions_this_week': Prescription.objects.filter(patient__clinic_id=clinic_id, date_prescribed__range=[start_week, today]).count(),
        'pending_bills': financial_stats['total_count'],
        'total_pending_amount': financial_stats['total_amount'],
        'outstanding_balance': financial_stats['total_amount'] - financial_stats['total_paid'],
    }

    # Get today's appointments for the clinic and user
    user_appointments = Appointment.objects.filter(
        clinic_id=clinic_id,
        date=today
    )
    
    # For non-admin/receptionist users, filter by provider
    if request.user.role not in ['ADMIN', 'RECEPTIONIST', 'NURSE']:
        user_appointments = user_appointments.filter(provider=request.user)
        
    user_appointments = user_appointments.order_by('-start_time')

    # Paginate appointments
    page = request.GET.get('page', 1)
    paginator = Paginator(user_appointments, 3)  # 3 appointments per page

    try:
        user_appointments_page = paginator.page(page)
    except PageNotAnInteger:
        user_appointments_page = paginator.page(1)
    except EmptyPage:
        user_appointments_page = paginator.page(paginator.num_pages)

    # Get recent patients for the clinic
    recent_patients = patients.order_by('-created_at')[:5]

    # Get unread notifications (including birthday notifications)
    read_global_ids = NotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
    notifications = Notification.objects.filter(
        (
            Q(user=request.user, is_read=False, clinic_id=clinic_id) |
            Q(user__isnull=True, clinic_id=clinic_id)
        )
    ).exclude(id__in=read_global_ids).order_by('-created_at')[:5]

    context = {
        'stats': stats,
        'user_appointments': user_appointments_page,
        'recent_patients': recent_patients,
        'notifications': notifications,
        'today': today,
        'clinic_id': clinic_id,
    }

    return render(request, 'dashboard.html', context)



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
        clinic_id = self.request.session.get('clinic_id')
        queryset = Appointment.objects.all()

        if clinic_id:
            queryset = queryset.filter(clinic_id=clinic_id)

        date_filter = self.request.GET.get('date', '')
        if date_filter:
            queryset = queryset.filter(date=date_filter)

        user = self.request.user
        if user.role not in ['ADMIN', 'RECEPTIONIST', 'NURSE']:
            queryset = queryset.filter(Q(provider=user) | Q(patient__created_by=user))

        return queryset.order_by('-date', '-start_time')



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
        
        # ✅ Manual logging
        log_action(
            self.request,
            'CREATE',
            appointment,
            details=f"Created appointment for {appointment.patient.full_name} on {appointment.date}"
        )

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
            
            # ✅ Fixed manual logging
            log_action(
                request,
                'CREATE',
                vitals,  # Changed from prescription to vitals
                details=f"Recorded vitals for {patient.full_name}"
            )

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
            
            # ✅ Add manual logging
            log_action(
                request,
                'CREATE',
                follow_up,
                details=f"Created follow-up for {patient.full_name}"
            )
            
            
            
            messages.success(request, "Follow-up created successfully.")
            return redirect('core:patient_detail', pk=patient_id)
    else:
        form = FollowUpForm()
    return render(request, 'DurielMedicApp/followup_form.html', {'form': form, 'patient': patient})



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
            
            # ✅ Manual logging
            log_action(
                request,
                'CREATE',
                record,
                details=f"Added medical record for {patient.full_name}"
            )
            
            
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
            
            # ✅ Manual logging
            log_action(
                request,
                'UPDATE',
                record,
                details=f"Updated medical record for {record.patient.full_name}"
            )
            
            
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

    # ✅ Manual logging
    log_action(
        request,
        'DELETE',
        record,
        details=f"Deleted medical record for {record.patient.full_name}"
    )

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
@role_required('ADMIN', 'DOCTOR', 'NURSE', 'OPTOMETRIST', 'PHYSIOTHERAPIST', 'RECEPTIONIST')
def mark_notification_read(request, pk):
    clinic_id = request.session.get('clinic_id')
    notification = get_object_or_404(Notification, pk=pk, clinic_id=clinic_id)
    
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
    
    # ✅ Fixed manual logging
    log_action(
        request,
        'UPDATE',
        appointment,
        details=f"Marked appointment #{appointment.id} as completed" 
    )
    
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
            
            # ✅ Add manual logging
            log_action(
                request,
                'CREATE',
                admission,
                details=f"Admitted patient {patient.full_name} to {ward}"
            )
            
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
    
    # ✅ Add manual logging
    log_action(
        request,
        'UPDATE',
        admission,
        details=f"Discharged patient {admission.patient.full_name}"
    )
    
    # Reset patient status
    patient.status = 'REGISTERED'
    patient.save()
    
    messages.success(request, "Patient discharged successfully")
    return redirect('core:patient_detail', pk=patient_id)




    
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
    clinic_id = request.session.get('clinic_id')
    if not clinic_id:
        messages.error(request, "No clinic selected. Please select a clinic first.")
        return redirect('core:select_clinic')

    # Filter patients and providers by clinic
    patients_qs = Patient.objects.filter(clinic_id=clinic_id)
    providers_qs = User.objects.filter(clinic__id=clinic_id, is_active=True)

    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        form.fields['patient'].queryset = patients_qs
        form.fields['provider'].queryset = providers_qs

        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.clinic_id = clinic_id  # Ensure correct clinic
            appointment.status = 'SCHEDULED'
            appointment.save()
            # Notify all staff in this clinic
            staff_users = User.objects.filter(clinic__id=clinic_id, is_active=True)
            for user in staff_users:
                Notification.objects.create(
                    user=user,
                    message=f"New appointment with {appointment.patient.full_name} on {appointment.date}",
                    link=reverse('DurielMedicApp:appointment_list'),
                    clinic_id=clinic_id
                )
            messages.success(request, 'Appointment scheduled successfully!')
            return redirect('DurielMedicApp:appointment_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = AppointmentForm(initial={'provider': request.user})
        form.fields['patient'].queryset = patients_qs
        form.fields['provider'].queryset = providers_qs

    return render(request, 'appointments/add_appointment.html', {
        'form': form,
        'title': 'Add New Appointment',
    })




# Notification Views


from django.core.mail import send_mail


def check_birthdays(clinic_id=None):
    today = date.today()
    patients = Patient.objects.filter(
        date_of_birth__month=today.month,
        date_of_birth__day=today.day
    )
    if clinic_id:
        patients = patients.filter(clinic_id=clinic_id)

    for patient in patients:
        # Check if we've already sent a birthday email today
        already_sent = Notification.objects.filter(
            message__icontains=f"{patient.full_name}'s birthday",
            created_at__date=today
        ).exists()
        
        if not already_sent:
            # Create notifications for staff
            staff_users = patient.clinic.staff.all() if hasattr(patient.clinic, 'staff') else []
            for user in staff_users:
                Notification.objects.create(
                    user=user,
                    message=f"Today is {patient.full_name}'s birthday!",
                    link=reverse('core:patient_detail', kwargs={'pk': patient.patient_id}),
                    clinic_id=patient.clinic_id
                )
            
            # Send email to patient if email exists
            if hasattr(patient, 'email') and patient.email:
                clinic_name = patient.clinic.name if patient.clinic else "Your Clinic"
                try:
                    send_mail(
                        'Happy Birthday!',
                        f'Dear {patient.full_name},\n\nHappy Birthday from {clinic_name}!',
                        settings.DEFAULT_FROM_EMAIL,
                        [patient.email],
                        fail_silently=True
                    )
                    # Create a notification to mark that we've sent the email
                    Notification.objects.create(
                        user=None,  # Global notification
                        message=f"Birthday email sent to {patient.full_name}",
                        clinic_id=patient.clinic_id
                    )
                except Exception as e:
                    print(f"Error sending birthday email: {str(e)}")




@login_required
def clear_notifications(request):
    clinic_id = request.session.get('clinic_id')
    if not clinic_id:
        messages.error(request, "No clinic selected")
        return redirect('core:select_clinic')
    
    # Delete user-specific notifications for this clinic
    request.user.notifications.filter(clinic_id=clinic_id).delete()

    # Mark global clinic notifications as read
    unread_globals = Notification.objects.filter(
        user__isnull=True,
        clinic_id=clinic_id
    ).exclude(
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
    
    # ✅ Add manual logging
    log_action(
        request,
        'UPDATE',
        patient,
        details=f"Began consultation for {patient.full_name}"
    )

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
            
            
            # ✅ Add manual logging for consultation completion
            log_action(
                request,
                'UPDATE',
                patient,
                details=f"Completed consultation for {patient.full_name}"
            )

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
        
        # ✅ Add manual logging
        log_action(
            request,
            'UPDATE',
            follow_up,
            details=f"Completed follow-up for {patient.full_name}"
        )
        
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
    clinic_id = request.session.get('clinic_id')
    if not clinic_id:
        messages.error(request, "No clinic selected. Please select a clinic first.")
        return redirect('core:select_clinic')

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
            return generate_appointment_report(start_date, end_date, clinic_id)
        elif report_type == 'patients':
            return generate_patient_report(start_date, end_date, clinic_id)
        elif report_type == 'financial':
            return generate_financial_report(start_date, end_date, clinic_id)

    # Dashboard Summary Stats
    appointment_stats = Appointment.objects.filter(
        clinic_id=clinic_id,
        date__range=[start_date.date(), end_date.date()]
    ).values('status').annotate(count=Count('id'))

    patient_stats = Patient.objects.filter(
        clinic_id=clinic_id,
        created_at__range=[start_date, end_date]
    ).aggregate(total=Count('patient_id'))

    financial_stats = Billing.objects.filter(
        clinic_id=clinic_id,
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


def generate_appointment_report(start_date, end_date, clinic_id):
    appointments = Appointment.objects.filter(
        clinic_id=clinic_id,
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


def generate_patient_report(start_date, end_date, clinic_id):
    patients = Patient.objects.filter(
        clinic_id=clinic_id,
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


def generate_financial_report(start_date, end_date, clinic_id):
    try:
        # Get all bills for the clinic within the date range
        bills = Billing.objects.filter(
            clinic_id=clinic_id,
            service_date__range=[start_date.date(), end_date.date()]
        ).select_related('patient').order_by('service_date')

        # Calculate totals for the report
        totals = bills.aggregate(
            total_billed=Sum('amount'),
            total_paid=Sum('paid_amount'),
        )
        totals['outstanding'] = (totals['total_billed'] or 0) - (totals['total_paid'] or 0)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="financial_report_'
            f'{start_date.date()}_to_{end_date.date()}.csv"'
        )

        writer = csv.writer(response)
        
        # Write header row
        writer.writerow(['Bill Date', 'Patient', 'Amount', 'Paid', 'Balance', 'Status', 'Description'])
        
        # Write bill details
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
        
        # Write totals row
        writer.writerow([])  # Empty row for separation
        writer.writerow(['TOTALS', '', 
                         totals['total_billed'] or 0, 
                         totals['total_paid'] or 0, 
                         totals['outstanding'], 
                         '', ''])

        return response

    except Exception as e:
        print(f"Error generating financial report: {str(e)}")
        return HttpResponse(
            "An error occurred while generating the report. Please try again later.",
            content_type='text/plain',
            status=500
        )