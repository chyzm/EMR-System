# DurielEyeApp/views.py

from datetime import date, timedelta, datetime, time
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Q, Count, Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView
from django.http import JsonResponse, HttpResponse
from django.utils.timezone import make_aware
from django.views.decorators.http import require_POST

from core.models import Patient, Billing
from .models import EyeAppointment, EyeMedicalRecord, EyeFollowUp, EyeNotification, EyeNotificationRead, EyeExam
from .forms import EyeAppointmentForm, EyeMedicalRecordForm, EyeFollowUpForm, EyeExamForm
from core.utils import log_action
from django.utils import timezone
from core.models import Patient
from django.db.models import Count 



# --------------------
# Permission Checks
# --------------------
def staff_check(user):
    return user.is_authenticated and user.role in ['ADMIN', 'DOCTOR', 'NURSE', 'OPTOMETRIST', 'RECEPTIONIST']

def admin_check(user):
    return user.is_authenticated and user.role == 'ADMIN'


# --------------------
# Dashboard
# --------------------
@login_required
@user_passes_test(staff_check, login_url='login')
def eye_dashboard(request):
    today = date.today()
    start_week = today - timedelta(days=today.weekday())
    end_week = start_week + timedelta(days=6)
    start_year = date(today.year, 1, 1)

    clinic_id = request.session.get('clinic_id')
    if not clinic_id and hasattr(request.user, 'primary_clinic') and request.user.primary_clinic:
        clinic_id = request.user.primary_clinic.id
        request.session['clinic_id'] = clinic_id

    # Patients
    patients = Patient.objects.filter(clinic_id=clinic_id, clinic__clinic_type='EYE')

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
        'today_appointments': EyeAppointment.objects.filter(clinic_id=clinic_id, date=today).count(),
        'completed_appointments_today': EyeAppointment.objects.filter(clinic_id=clinic_id, date=today, status='COMPLETED').count(),
        'week_appointments': EyeAppointment.objects.filter(clinic_id=clinic_id, date__range=[start_week, end_week]).count(),
        'pending_bills': financial_stats['total_count'],
        'total_pending_amount': financial_stats['total_amount'],
        'outstanding_balance': financial_stats['total_amount'] - financial_stats['total_paid'],
    }

    # Appointments for the user
    user_appointments = EyeAppointment.objects.filter(clinic_id=clinic_id, date=today)
    if request.user.role not in ['ADMIN', 'RECEPTIONIST', 'NURSE']:
        user_appointments = user_appointments.filter(provider=request.user)
    user_appointments = user_appointments.order_by('-start_time')

    paginator = Paginator(user_appointments, 3)
    page = request.GET.get('page', 1)
    try:
        user_appointments_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        user_appointments_page = paginator.page(1)

    # Recent patients
    recent_patients = patients.order_by('-created_at')[:5]

    # Notifications
    read_global_ids = EyeNotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
    notifications = EyeNotification.objects.filter(
        Q(user=request.user, is_read=False, clinic_id=clinic_id) |
        Q(user__isnull=True, clinic_id=clinic_id)
    ).exclude(id__in=read_global_ids).order_by('-created_at')[:5]

    # appointments = EyeAppointment.objects.filter(clinic_id=clinic_id, date=today)
    appointments = EyeAppointment.objects.filter(clinic_id=clinic_id, date=today).exclude(id__isnull=True)

    return render(request, 'Eye/eye_dashboard.html', {
        'stats': stats,
        'user_appointments': user_appointments_page,
        'recent_patients': recent_patients,
        'notifications': notifications,
        'today': today,
        'clinic_id': clinic_id,
        'appointments': appointments,  # add this
    })


# --------------------
# Appointments
# --------------------
class EyeAppointmentListView(ListView):
    model = EyeAppointment
    template_name = 'eye/appointments/appointment_list.html'
    context_object_name = 'appointments'
    paginate_by = 10

    def get_queryset(self):
        clinic_id = self.request.session.get('clinic_id')
        qs = EyeAppointment.objects.filter(clinic_id=clinic_id)
        date_filter = self.request.GET.get('date', '')
        if date_filter:
            qs = qs.filter(date=date_filter)
        user = self.request.user
        if user.role not in ['ADMIN', 'RECEPTIONIST', 'NURSE']:
            qs = qs.filter(Q(provider=user) | Q(patient__created_by=user))
        return qs.order_by('-date', '-start_time')


class EyeAppointmentCreateView(CreateView):
    model = EyeAppointment
    form_class = EyeAppointmentForm
    template_name = 'eye/appointments/appointment_form.html'
    success_url = reverse_lazy('DurielEyeApp:appointment_list')

    def get_initial(self):
        """Pre-fill provider if desired"""
        initial = super().get_initial()
        initial['provider'] = self.request.user
        return initial

    def form_valid(self, form):
        # Set provider and clinic_id automatically
        form.instance.provider = self.request.user
        form.instance.clinic_id = self.request.session.get('clinic_id')

        # Debug: check values
        print("Clinic ID:", form.instance.clinic_id)
        print("Provider:", form.instance.provider)

        appointment = form.save()
        log_action(
            self.request, 'CREATE', appointment,
            details=f"Created eye appointment for {appointment.patient.full_name}"
        )
        messages.success(self.request, "Appointment scheduled successfully!")
        return super().form_valid(form)

    def form_invalid(self, form):
        # Print form errors for debugging
        print(form.errors)
        messages.error(self.request, "There was a problem with your submission.")
        return super().form_invalid(form)



@login_required
def eye_appointment_detail(request, pk):
    appointment = get_object_or_404(EyeAppointment, pk=pk)
    return render(request, 'eye/appointments/appointment_detail.html', {'appointment': appointment})


def eye_appointment_update(request, appointment_id):
    appointment = get_object_or_404(EyeAppointment, id=appointment_id)

    # Get user's clinics (supports multiple clinics)
    user_clinics = request.user.clinic.all()  # queryset of clinics

    if request.method == "POST":
        form = EyeAppointmentForm(request.POST, instance=appointment, clinics=user_clinics)
        if form.is_valid():
            form.save()
            messages.success(request, "Eye appointment updated successfully.")
            return redirect('DurielEyeApp:appointment_detail', pk=appointment.id)
    else:
        form = EyeAppointmentForm(instance=appointment, clinics=user_clinics)

    return render(request, 'eye/appointments/appointment_form.html', {'form': form, 'appointment': appointment})


def eye_appointment_delete(request, pk):
    appointment = get_object_or_404(EyeAppointment, id=pk)

    if request.method == "POST":
        appointment.delete()
        messages.success(request, "Eye appointment deleted successfully.")
        return redirect('DurielEyeApp:eye_appointment_list')  # Make sure you have this URL name

    return render(request, 'eye_clinic/confirm_delete.html', {'appointment': appointment})


def mark_eye_appointment_completed(request, appointment_id):
    """Mark an eye appointment as completed."""
    appointment = get_object_or_404(EyeAppointment, id=appointment_id)
    appointment.status = 'COMPLETED'  # Make sure 'COMPLETED' exists in your status choices
    appointment.save()
    messages.success(request, f"Appointment for {appointment.patient} marked as completed.")
    return redirect('DurielEyeApp:eye_appointment_list')


def mark_eye_appointment_cancelled(request, appointment_id):
    """Mark an eye appointment as cancelled."""
    appointment = get_object_or_404(EyeAppointment, id=appointment_id)
    appointment.status = 'CANCELLED'  # Make sure this value exists in your status choices
    appointment.save()
    messages.warning(request, f"Appointment for {appointment.patient} has been cancelled.")
    return redirect('DurielEyeApp:eye_appointment_list')



def check_eye_appointment_availability(request):
    """Check if an appointment slot is available for a given date/time/provider."""
    date_str = request.GET.get('date')
    start_time_str = request.GET.get('start_time')
    provider_id = request.GET.get('provider_id')

    if not date_str or not start_time_str or not provider_id:
        return JsonResponse({'available': False, 'error': 'Missing required parameters'}, status=400)

    date = parse_date(date_str)
    start_time = parse_time(start_time_str)

    # Check for conflicting appointments
    conflict_exists = EyeAppointment.objects.filter(
        date=date,
        start_time=start_time,
        provider_id=provider_id
    ).exists()

    return JsonResponse({'available': not conflict_exists})


# --------------------
# Eye Exams
# --------------------
@login_required
def record_eye_exam(request, appointment_id):
    clinic_id = request.session.get('clinic_id')
    appointment = get_object_or_404(EyeAppointment, pk=appointment_id, clinic_id=clinic_id)

    if request.method == 'POST':
        form = EyeExamForm(request.POST)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.patient = appointment.patient  # assign the patient
            exam.appointment = appointment      # ✅ assign appointment
            exam.created_by = request.user      # assign who created it
            exam.save()
            messages.success(request, f"Eye exam for {exam.patient.full_name} recorded successfully.")
            # return redirect('DurielEyeApp:appointment_detail', pk=appointment.pk)
            log_action(request, 'CREATE', exam, details=f"Recorded eye exam for {exam.patient.full_name}")
            return redirect('DurielEyeApp:begin_consultation', patient_id=appointment.patient.patient_id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = EyeExamForm()

    context = {
        'form': form,
        'appointment': appointment
    }
    return render(request, 'eye/exams/record_exam.html', context)



@login_required
def edit_eye_exam(request, exam_id):
    clinic_id = request.session.get('clinic_id')
    exam = get_object_or_404(EyeExam, pk=exam_id, patient__clinic_id=clinic_id)

    if request.method == 'POST':
        form = EyeExamForm(request.POST, instance=exam)
        if form.is_valid():
            form.save()
            log_action(request, 'UPDATE', exam, details=f"Updated eye exam for {exam.patient.full_name}")
            messages.success(request, f"Eye exam for {exam.patient.full_name} updated successfully.")
            return redirect('DurielEyeApp:begin_consultation', patient_id=exam.patient.patient_id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = EyeExamForm(instance=exam)

    return render(request, 'eye/exams/edit_eye_exam.html', {'form': form, 'exam': exam})







def delete_eye_exam(request, exam_id):
    record = get_object_or_404(EyeExam, pk=exam_id)

    if request.method == "POST":
        record.delete()
        return redirect('core:patient_detail', pk=record.patient.pk)

    return render(request, 'eye/exams/delete_eye_exam.html', {'object': record})




# --------------------
# Medical Records
# --------------------
@login_required
def add_eye_medical_record(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id, clinic__clinic_type='EYE')

    if request.method == 'POST':
        form = EyeMedicalRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.patient = patient
            record.clinic = patient.clinic
            record.created_by = request.user
            record.save()

            # Log action
            log_action(
                request,
                'CREATE',
                record,
                details=f"Added eye medical record for {patient.full_name}"
            )

            messages.success(request, "Medical record added successfully!")
            # Use 'pk' to match URL pattern
            return redirect('core:patient_detail', pk=patient_id)
        else:
            messages.error(request, f"Form errors: {form.errors}")
    else:
        form = EyeMedicalRecordForm()

    return render(request, 'eye/medical_records/add_record.html', {'form': form, 'patient': patient})




def edit_eye_medical_record(request, record_id):
    record = get_object_or_404(EyeMedicalRecord, id=record_id)
    
    if request.method == 'POST':
        form = EyeMedicalRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            # return redirect('core:patient_detail', pk=record.patient.pk)  # Change to where you want to redirect
            return redirect('core:patient_detail', pk=record.patient.pk)
    else:
        form = EyeMedicalRecordForm(instance=record)
        

    return render(request, 'eye/medical_records/edit_eye_medical_record.html', {'form': form, 'record': record})






def delete_eye_medical_record(request, pk):
    record = get_object_or_404(MedicalRecord, pk=pk)

    if request.method == "POST":
        record.delete()
        return redirect('core:patient_detail', pk=record.patient.pk)

    return render(request, 'eye/medical_records/delete_medical_record', {'object': record})



#-------------------------
#  Consultation
#-------------------------

@login_required
def begin_eye_consultation(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id)
    # Optionally create or get an appointment here
    appointment = EyeAppointment.objects.filter(patient=patient).order_by('-date').first()

    context = {
        'patient': patient,
        'appointment': appointment
    }
    return render(request, 'eye/consultation/begin_consultation.html', context)


@login_required
def complete_eye_consultation(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id)
    
    # Optionally mark the last appointment as completed
    appointment = EyeAppointment.objects.filter(patient=patient).order_by('-date').first()
    if appointment:
        appointment.status = 'COMPLETED'
        appointment.save()
        messages.success(request, f"Consultation for {patient.full_name} marked as completed.")
    else:
        messages.warning(request, f"No active appointment found for {patient.full_name}.")

    return redirect('core:patient_detail', pk=patient.pk)


# --------------------
# Follow-ups
# --------------------
class EyeFollowUpListView(ListView):
    model = EyeFollowUp
    template_name = 'eye/follow_up/followup_list.html'
    context_object_name = 'followups'
    paginate_by = 10

    def get_queryset(self):
        return EyeFollowUp.objects.filter(patient__clinic__clinic_type='EYE').order_by('scheduled_date', 'scheduled_time')


class EyeFollowUpCreateView(CreateView):
    model = EyeFollowUp
    form_class = EyeFollowUpForm
    template_name = 'eye/followup/followup_form.html'
    success_url = reverse_lazy('DurielEyeApp:followup_list')

    def form_valid(self, form):
        # Set clinic_id from session
        clinic_id = self.request.session.get('clinic_id')
        if not clinic_id:
            messages.error(self.request, "No clinic selected.")
            return redirect('core:select_clinic')

        form.instance.clinic_id = clinic_id
        form.instance.provider = self.request.user

        # Save the instance
        followup = form.save()
        log_action(self.request, 'CREATE', followup, f"Created follow-up for {followup.patient.full_name}")
        messages.success(self.request, "Follow-up created successfully!")
        return redirect(self.success_url)



class EyeFollowUpUpdateView(UpdateView):
    model = EyeFollowUp
    form_class = EyeFollowUpForm
    template_name = 'eye/follow_up/followup_form.html'
    

@login_required
def schedule_eye_follow_up(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id)

    if request.method == "POST":
        form = EyeFollowUpForm(request.POST, clinic_id=patient.clinic_id)
        if form.is_valid():
            follow_up = form.save(commit=False)
            follow_up.patient = patient
            follow_up.save()
            messages.success(request, f"Follow-up scheduled for {patient.full_name}.")
            return redirect('core:patient_detail', patient_id=patient.patient_id)
    else:
        form = EyeFollowUpForm(clinic_id=patient.clinic_id)

    return render(request, "eye/follow_up/schedule_follow_up.html", {
        "form": form,
        "patient": patient
    })


@login_required
def complete_eye_follow_up(request, pk):
    clinic_id = request.session.get('clinic_id')
    followup = get_object_or_404(EyeFollowUp, pk=pk, clinic_id=clinic_id)

    if not followup.completed:
        followup.completed = True
        followup.completed_at = timezone.now()  # if you have a completed_at field
        followup.save()
        messages.success(request, f"Follow-up for {followup.patient.full_name} marked as completed.")
    else:
        messages.info(request, "Follow-up is already completed.")

    return redirect('DurielEyeApp:followup_list')


# --------------------
# Notifications
# --------------------
@login_required
def mark_eye_notification_read(request, pk):
    clinic_id = request.session.get('clinic_id')
    notification = get_object_or_404(EyeNotification, pk=pk, clinic_id=clinic_id)
    if notification.user == request.user:
        notification.is_read = True
        notification.save()
    elif notification.user is None:
        EyeNotificationRead.objects.get_or_create(user=request.user, notification=notification)
    return redirect(request.META.get('HTTP_REFERER', 'DurielEyeApp:dashboard'))


@login_required
def clear_eye_notifications(request):
    clinic_id = request.session.get('clinic_id')
    request.user.eye_notifications.filter(clinic_id=clinic_id).delete()
    unread_globals = EyeNotification.objects.filter(user__isnull=True, clinic_id=clinic_id).exclude(
        id__in=EyeNotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
    )
    EyeNotificationRead.objects.bulk_create(
        [EyeNotificationRead(user=request.user, notification=n) for n in unread_globals],
        ignore_conflicts=True
    )
    messages.success(request, "Notifications cleared")
    return redirect(request.META.get('HTTP_REFERER', 'DurielEyeApp:dashboard'))


#--------------------
# Reports
#--------------------

# Add these imports at the top of your views.py file
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.timezone import make_aware
from datetime import datetime, time, timedelta



# Make sure you have these imports at the top of your views.py
import csv


# Complete, clean version of the eye report functions
# Make sure you have these imports at the top of your views.py
import csv
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.timezone import make_aware
from datetime import datetime, time, timedelta

# Import models
from core.models import Patient, Billing  # Patient and Billing from core app
from .models import EyeAppointment  # Your local eye models

@login_required
@user_passes_test(admin_check, login_url='login')
def generate_eye_report(request):
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
            return generate_eye_appointment_report(start_date, end_date, clinic_id)
        elif report_type == 'patients':
            return generate_eye_patient_report(start_date, end_date, clinic_id)
        elif report_type == 'financial':
            return generate_eye_financial_report(start_date, end_date, clinic_id)

    # Dashboard Summary Stats
    try:
        appointment_stats = EyeAppointment.objects.filter(
            clinic_id=clinic_id,
            date__range=[start_date.date(), end_date.date()]
        ).values('status').annotate(count=Count('pk'))
    except Exception as e:
        appointment_stats = []
        print(f"Appointment stats error: {e}")

    # Use Patient from core.models and filter for eye-related patients
    patient_stats = Patient.objects.filter(
        clinic_id=clinic_id,
        created_at__range=[start_date, end_date]
    ).aggregate(total=Count('pk'))

    # Financial stats - using centralized core Billing model
    try:
        print(f"DEBUG: Using clinic_id = {clinic_id}")
        print(f"DEBUG: Date range = {start_date.date()} to {end_date.date()}")
        
        # Debug: Check total bills for this clinic (without date filter)
        total_bills_for_clinic = Billing.objects.filter(clinic_id=clinic_id).count()
        print(f"DEBUG: Total Billing records for clinic {clinic_id}: {total_bills_for_clinic}")
        
        # Get financial stats for this clinic and date range
        financial_stats = Billing.objects.filter(
            clinic_id=clinic_id,
            service_date__range=[start_date.date(), end_date.date()]
        ).aggregate(
            total_amount=Sum('amount'),
            total_paid=Sum('paid_amount')
        )
        
        # Debug: Check how many bills in date range
        bills_in_range = Billing.objects.filter(
            clinic_id=clinic_id,
            service_date__range=[start_date.date(), end_date.date()]
        ).count()
        print(f"DEBUG: Billing records in date range: {bills_in_range}")
        print(f"DEBUG: Financial stats result: {financial_stats}")
        
        # Ensure we have default values if None
        if not financial_stats['total_amount']:
            financial_stats['total_amount'] = 0
        if not financial_stats['total_paid']:
            financial_stats['total_paid'] = 0
            
        # Debug: Show some sample bills if any exist
        if bills_in_range > 0:
            sample_bills = Billing.objects.filter(
                clinic_id=clinic_id,
                service_date__range=[start_date.date(), end_date.date()]
            )[:3]
            for i, bill in enumerate(sample_bills, 1):
                print(f"DEBUG: Sample bill {i} - Amount: {getattr(bill, 'amount', 'N/A')}, Paid: {getattr(bill, 'paid_amount', 'N/A')}, Date: {getattr(bill, 'service_date', 'N/A')}")
            
    except Exception as e:
        financial_stats = {'total_amount': 0, 'total_paid': 0}
        print(f"Financial stats error: {e}")
        
        # Additional debugging - check if Billing model exists and has expected fields
        try:
            all_bills = Billing.objects.filter(clinic_id=clinic_id)
            print(f"Total bills for clinic {clinic_id}: {all_bills.count()}")
            if all_bills.exists():
                sample_bill = all_bills.first()
                print(f"Available fields in Billing model: {[f.name for f in sample_bill._meta.fields]}")
                print(f"Sample bill data: clinic_id={sample_bill.clinic_id}")
        except Exception as debug_error:
            print(f"Debug error: {debug_error}")

    context = {
        'start_date': start_date.date(),
        'end_date': end_date.date(),
        'appointment_stats': appointment_stats,
        'patient_stats': patient_stats,
        'financial_stats': financial_stats,
    }

    return render(request, 'eye/reports/generate_eye_report.html', context)


def generate_eye_appointment_report(start_date, end_date, clinic_id):
    try:
        appointments = EyeAppointment.objects.filter(
            clinic_id=clinic_id,
            date__range=[start_date.date(), end_date.date()]
        ).select_related('patient', 'provider', 'clinic').order_by('date')

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="eye_appointments_{start_date.date()}_to_{end_date.date()}.csv"'

        writer = csv.writer(response)
        writer.writerow(['Date', 'Time', 'Patient', 'Provider', 'Status', 'Diagnosis'])

        for appt in appointments:
            # Handle time fields safely
            time_display = 'N/A'
            if hasattr(appt, 'start_time') and hasattr(appt, 'end_time'):
                time_display = f"{appt.start_time} - {appt.end_time}"
            elif hasattr(appt, 'time'):
                time_display = str(appt.time)
            
            writer.writerow([
                appt.date,
                time_display,
                appt.patient.full_name if appt.patient else 'N/A',
                appt.provider.get_full_name() if appt.provider and hasattr(appt.provider, 'get_full_name') else (str(appt.provider) if appt.provider else 'N/A'),
                appt.get_status_display() if hasattr(appt, 'get_status_display') else getattr(appt, 'status', 'N/A'),
                getattr(appt, 'diagnosis', 'N/A')
            ])

        return response
    except Exception as e:
        response = HttpResponse(content_type='text/plain')
        response.write(f"Error generating appointment report: {str(e)}")
        return response


def generate_eye_patient_report(start_date, end_date, clinic_id):
    # Use Patient from core.models instead of EyePatient
    patients = Patient.objects.filter(
        clinic_id=clinic_id,
        created_at__range=[start_date, end_date]
    ).order_by('created_at')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="eye_patients_{start_date.date()}_to_{end_date.date()}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Patient ID', 'Full Name', 'Gender', 'Date of Birth', 'Created At'])

    for patient in patients:
        writer.writerow([
            getattr(patient, 'patient_id', 'N/A'),
            patient.full_name,
            getattr(patient, 'gender', 'N/A'),
            getattr(patient, 'date_of_birth', 'N/A'),
            patient.created_at
        ])

    return response


def generate_eye_financial_report(start_date, end_date, clinic_id):
    try:
        print(f"DEBUG: Generating financial report for clinic_id = {clinic_id}")
        print(f"DEBUG: Date range = {start_date.date()} to {end_date.date()}")
        
        # Get all billing records for this clinic in the date range
        billings = Billing.objects.filter(
            clinic_id=clinic_id,
            service_date__range=[start_date.date(), end_date.date()]
        ).select_related('patient').order_by('service_date')
        
        print(f"DEBUG: Found {billings.count()} billing records")
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="eye_financials_{start_date.date()}_to_{end_date.date()}.csv"'

        writer = csv.writer(response)
        writer.writerow(['Date', 'Patient', 'Service', 'Amount', 'Paid Amount', 'Balance'])

        total_amount = 0
        total_paid = 0
        
        for bill in billings:
            amount = getattr(bill, 'amount', 0) or 0
            paid_amount = getattr(bill, 'paid_amount', 0) or 0
            balance = amount - paid_amount
            
            total_amount += amount
            total_paid += paid_amount
            
            writer.writerow([
                getattr(bill, 'service_date', 'N/A'),
                bill.patient.full_name if bill.patient else 'N/A',
                getattr(bill, 'service_name', getattr(bill, 'description', getattr(bill, 'service_type', 'N/A'))),
                amount,
                paid_amount,
                balance
            ])
        
        # Add summary row
        writer.writerow([])
        writer.writerow(['SUMMARY', '', '', total_amount, total_paid, total_amount - total_paid])
        
        print(f"DEBUG: Report generated - Total Amount: {total_amount}, Total Paid: {total_paid}")

        return response
        
    except Exception as e:
        print(f"ERROR generating financial report: {str(e)}")
        # Create error report
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="eye_financials_{start_date.date()}_to_{end_date.date()}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Date', 'Patient', 'Service', 'Amount', 'Paid Amount', 'Balance'])
        writer.writerow([f'Error: {str(e)}', '', '', '', '', ''])
        writer.writerow([f'No financial data available for clinic {clinic_id}', '', '', '', '', ''])
        return response