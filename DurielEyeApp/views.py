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
from django.conf import settings  # ADD THIS IMPORT

from core.models import Patient, Billing, CustomUser, Notification, NotificationRead, Prescription
from .models import EyeAppointment, EyeMedicalRecord, EyeFollowUp, EyeExam
from .forms import EyeAppointmentForm, EyeMedicalRecordForm, EyeFollowUpForm, EyeExamForm
from core.utils import log_action
from django.utils import timezone
from core.models import Patient
from django.db.models import Count 
from django.contrib import messages
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.views.generic import CreateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from .models import EyeAppointment
from .forms import EyeAppointmentForm
from core.utils import log_action
from core.decorators import clinic_selected_required
from django.db.models import Prefetch






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
from django.shortcuts import render

# @login_required
# @user_passes_test(staff_check, login_url='login')
# def eye_dashboard(request):
#     today = date.today()
#     start_week = today - timedelta(days=today.weekday())
#     end_week = start_week + timedelta(days=6)
#     start_year = date(today.year, 1, 1)

#     clinic_id = request.session.get('clinic_id')
#     if not clinic_id and hasattr(request.user, 'primary_clinic') and request.user.primary_clinic:
#         clinic_id = request.user.primary_clinic.id
#         request.session['clinic_id'] = clinic_id
        
#     # --- Birthday notifications ---
#     # ENSURE THIS RUNS EVERY DASHBOARD LOAD
#     if clinic_id:  # Only run if we have a clinic_id
#         check_birthdays(clinic_id)

#     # Patients - FIXED: Filter properly for eye clinic
#     patients = Patient.objects.all()
#     if clinic_id:
#         patients = patients.filter(clinic_id=clinic_id)

#     # Financial stats
#     financial_stats = Billing.objects.filter(clinic_id=clinic_id, status='PENDING').aggregate(
#         total_count=Count('id'),
#         total_amount=Coalesce(Sum('amount', output_field=DecimalField()), Value(0, output_field=DecimalField())),
#         total_paid=Coalesce(Sum('paid_amount', output_field=DecimalField()), Value(0, output_field=DecimalField()))
#     )

#     stats = {
#         'total_patients': patients.count(),
#         'new_patients_this_week': patients.filter(created_at__date__range=[start_week, today]).count(),
#         'new_patients_this_year': patients.filter(created_at__date__gte=start_year).count(),
#         'today_appointments': EyeAppointment.objects.filter(clinic_id=clinic_id, date=today).count(),
#         'completed_appointments_today': EyeAppointment.objects.filter(clinic_id=clinic_id, date=today, status='COMPLETED').count(),
#         'week_appointments': EyeAppointment.objects.filter(clinic_id=clinic_id, date__range=[start_week, end_week]).count(),
#         'pending_prescriptions': Prescription.objects.filter(patient__clinic_id=clinic_id, is_active=True).count(),
#         'new_prescriptions_this_week': Prescription.objects.filter(patient__clinic_id=clinic_id, date_prescribed__range=[start_week, today]).count(),
#         'pending_bills': financial_stats['total_count'],
#         'total_pending_amount': financial_stats['total_amount'],
#         'outstanding_balance': financial_stats['total_amount'] - financial_stats['total_paid'],
#     }

#     # Appointments for the user
#     user_appointments = EyeAppointment.objects.filter(
#         clinic_id=clinic_id, 
#         date=today
#     ).select_related('patient', 'provider', 'clinic').order_by('start_time')

#     if request.user.role not in ['ADMIN', 'RECEPTIONIST', 'NURSE']:
#         user_appointments = user_appointments.filter(provider=request.user)

#     paginator = Paginator(user_appointments, 3)  # Changed to 3 to match DurielMedicApp
#     page = request.GET.get('page', 1)
    
#     try:
#         user_appointments_page = paginator.page(page)
#     except (PageNotAnInteger, EmptyPage):
#         user_appointments_page = paginator.page(1)

#     # Recent patients
#     recent_patients = patients.order_by('-created_at')[:5]

#     # Notifications - FIXED: Use same logic as DurielMedicApp
#     read_global_ids = NotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
#     notifications = Notification.objects.filter(
#         (
#             Q(user=request.user, is_read=False, clinic_id=clinic_id) |
#             Q(user__isnull=True, clinic_id=clinic_id)
#         )
#     ).exclude(id__in=read_global_ids).order_by('-created_at')[:5]

#     # All appointments for today
#     appointments = EyeAppointment.objects.filter(clinic_id=clinic_id, date=today).exclude(id__isnull=True)

#     context = {
#         'stats': stats,
#         'user_appointments': user_appointments_page,
#         'recent_patients': recent_patients,
#         'notifications': notifications,
#         'today': today,
#         'clinic_id': clinic_id,
#         'appointments': appointments,
#     }

#     return render(request, 'eye/eye_dashboard.html', context)



@login_required
@clinic_selected_required
def eye_dashboard(request):
    clinic_id = request.session.get('clinic_id')
    today = timezone.now().date()
    
    # Get today's eye appointments
    user_appointments = EyeAppointment.objects.filter(
        clinic_id=clinic_id,
        date=today
    ).select_related('patient', 'clinic').order_by('start_time')
    
    # Statistics calculations
    stats = {
        'today_appointments': user_appointments.count(),
        'completed_appointments_today': user_appointments.filter(status='COMPLETED').count(),
        'week_appointments': EyeAppointment.objects.filter(
            clinic_id=clinic_id,
            date__week=today.isocalendar()[1],
            date__year=today.year
        ).count(),
        'total_patients': Patient.objects.filter(clinic_id=clinic_id).count(),
        'new_patients_this_week': Patient.objects.filter(
            clinic_id=clinic_id,
            created_at__gte=today - timedelta(days=7)
        ).count(),
        'new_patients_this_year': Patient.objects.filter(
            clinic_id=clinic_id,
            created_at__year=today.year
        ).count(),
        'pending_prescriptions': Prescription.objects.filter(
            patient__clinic_id=clinic_id,
            is_active=True
        ).count(),
        'new_prescriptions_this_week': Prescription.objects.filter(
            patient__clinic_id=clinic_id,
            date_prescribed__gte=today - timedelta(days=7)
        ).count(),
        'pending_bills': Billing.objects.filter(
            clinic_id=clinic_id,
            status__in=['PENDING', 'PARTIAL']
        ).count(),
        'total_pending_amount': Billing.objects.filter(
            clinic_id=clinic_id,
            status__in=['PENDING', 'PARTIAL']
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'outstanding_balance': Billing.objects.filter(
            clinic_id=clinic_id,
            status__in=['PENDING', 'PARTIAL']
        ).aggregate(total=Sum('amount'))['total'] or 0,
    }
    
    # Get recent patients with their last appointment
    # This is the key fix - we're prefetching the appointments and ordering them
    recent_patients = Patient.objects.filter(
        clinic_id=clinic_id
    ).prefetch_related(
        Prefetch(
            'appointments',  # regular appointments
            queryset=EyeAppointment.objects.order_by('-date', '-start_time'),
            to_attr='ordered_appointments'
        ),
        Prefetch(
            'eye_appointments',  # eye appointments
            queryset=EyeAppointment.objects.order_by('-date', '-start_time'),
            to_attr='ordered_eye_appointments'
        )
    ).order_by('-created_at')[:10]
    
    # For each patient, find their most recent appointment (from either type)
    for patient in recent_patients:
        # Get the most recent appointment from both regular and eye appointments
        last_regular = patient.ordered_appointments[0] if patient.ordered_appointments else None
        last_eye = patient.ordered_eye_appointments[0] if patient.ordered_eye_appointments else None
        
        # Determine which is more recent
        if last_regular and last_eye:
            if last_eye.date >= last_regular.date:
                patient.last_appointment = last_eye
            else:
                patient.last_appointment = last_regular
        elif last_eye:
            patient.last_appointment = last_eye
        elif last_regular:
            patient.last_appointment = last_regular
        else:
            patient.last_appointment = None
    
    # Get patients for prescription dropdown (if needed)
    patients = Patient.objects.filter(clinic_id=clinic_id)
    
    # Get notifications
    notifications = request.user.notifications.filter(
        clinic_id=clinic_id,
        is_read=False
    ).order_by('-created_at')[:10]
    
    context = {
        'user_appointments': user_appointments,
        'stats': stats,
        'recent_patients': recent_patients,
        'patients': patients,
        'notifications': notifications,
        'today': today,
    }
    
    return render(request, 'eye/eye_dashboard.html', context)



    
    
    
    
    

# @login_required
# @user_passes_test(staff_check, login_url='login')
# def eye_dashboard(request):
#     today = date.today()
#     start_week = today - timedelta(days=today.weekday())
#     end_week = start_week + timedelta(days=6)
#     start_year = date(today.year, 1, 1)

#     clinic_id = request.session.get('clinic_id')
#     if not clinic_id and hasattr(request.user, 'primary_clinic') and request.user.primary_clinic:
#         clinic_id = request.user.primary_clinic.id
#         request.session['clinic_id'] = clinic_id

#     # Patients
#     patients = Patient.objects.filter(clinic_id=clinic_id, clinic__clinic_type='EYE')

#     # Financial stats
#     financial_stats = Billing.objects.filter(clinic_id=clinic_id, status='PENDING').aggregate(
#         total_count=Count('id'),
#         total_amount=Coalesce(Sum('amount', output_field=DecimalField()), Value(0, output_field=DecimalField())),
#         total_paid=Coalesce(Sum('paid_amount', output_field=DecimalField()), Value(0, output_field=DecimalField()))
#     )

#     stats = {
#         'total_patients': patients.count(),
#         'new_patients_this_week': patients.filter(created_at__date__range=[start_week, today]).count(),
#         'new_patients_this_year': patients.filter(created_at__date__gte=start_year).count(),
#         'today_appointments': EyeAppointment.objects.filter(clinic_id=clinic_id, date=today).count(),
#         'completed_appointments_today': EyeAppointment.objects.filter(clinic_id=clinic_id, date=today, status='COMPLETED').count(),
#         'week_appointments': EyeAppointment.objects.filter(clinic_id=clinic_id, date__range=[start_week, end_week]).count(),
#         'pending_bills': financial_stats['total_count'],
#         'total_pending_amount': financial_stats['total_amount'],
#         'outstanding_balance': financial_stats['total_amount'] - financial_stats['total_paid'],
#     }

#     # Appointments for the user
#     user_appointments = EyeAppointment.objects.filter(clinic_id=clinic_id, date=today)
#     if request.user.role not in ['ADMIN', 'RECEPTIONIST', 'NURSE']:
#         user_appointments = user_appointments.filter(provider=request.user)
#     user_appointments = user_appointments.order_by('-start_time')

#     paginator = Paginator(user_appointments, 3)
#     page = request.GET.get('page', 1)
#     try:
#         user_appointments_page = paginator.page(page)
#     except (PageNotAnInteger, EmptyPage):
#         user_appointments_page = paginator.page(1)

#     # Recent patients
#     recent_patients = patients.order_by('-created_at')[:5]

#     # Notifications
#     read_global_ids = NotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
#     notifications = Notification.objects.filter(
#         Q(user=request.user, is_read=False, clinic_id=clinic_id) |
#         Q(user__isnull=True, clinic_id=clinic_id)
#     ).exclude(id__in=read_global_ids).order_by('-created_at')[:5]

#     # appointments = EyeAppointment.objects.filter(clinic_id=clinic_id, date=today)
#     appointments = EyeAppointment.objects.filter(clinic_id=clinic_id, date=today).exclude(id__isnull=True)

#     return render(request, 'Eye/eye_dashboard.html', {
#         'stats': stats,
#         'user_appointments': user_appointments_page,
#         'recent_patients': recent_patients,
#         'notifications': notifications,
#         'today': today,
#         'clinic_id': clinic_id,
#         'appointments': appointments,  # add this
#     })


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





# class EyeAppointmentCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
#     model = EyeAppointment
#     form_class = EyeAppointmentForm
#     template_name = 'eye/appointments/appointment_form.html'
#     success_url = reverse_lazy('DurielEyeApp:appointment_list')

#     def test_func(self):
#         return self.request.user.role in ['ADMIN', 'DOCTOR', 'RECEPTIONIST', 'OPTOMETRIST']

#     def get_form_kwargs(self):
#         kwargs = super().get_form_kwargs()
#         kwargs['clinic_id'] = self.request.session.get('clinic_id')
#         # kwargs['request'] = self.request  # Pass request to the form
#         return kwargs

#     def get_form(self, form_class=None):
#         form = super().get_form(form_class)
#         # Limit provider choices to staff in the same clinic
#         clinic_id = self.request.session.get('clinic_id')
#         if clinic_id:
#             form.fields['provider'].queryset = CustomUser.objects.filter(
#                 clinic__id=clinic_id,
#                 is_active=True,
#                 role__in=['DOCTOR', 'OPTOMETRIST', 'ADMIN']  # Only show appropriate roles
#             ).order_by('first_name', 'last_name')
#         return form

#     def form_valid(self, form):
#         clinic_id = self.request.session.get('clinic_id')
#         if not clinic_id:
#             messages.error(self.request, "No clinic selected")
#             return redirect('core:select_clinic')

#         # Set clinic and save appointment
#         form.instance.clinic_id = clinic_id
#         appointment = form.save()

#         # Create notification for staff in the same clinic
#         staff_users = CustomUser.objects.filter(
#             clinic__id=clinic_id,
#             is_active=True
#          ) #.exclude(id=appointment.provider.id)  # Exclude the provider

#         for user in staff_users:
#             Notification.objects.create(
#                 user=user,
#                 message=f"New eye appointment with {appointment.patient.full_name} on {appointment.date}",
#                 link=reverse('DurielEyeApp:appointment_list'),
#                 clinic_id=clinic_id,
#                 object_id=str(appointment.id),  # Unique identifier
#                 app_name='eye'
#             )

#         # Also notify the provider if they're not the one creating the appointment
#         if appointment.provider != self.request.user:
#             Notification.objects.create(
#                 user=appointment.provider,
#                 message=f"You have a new appointment with {appointment.patient.full_name} on {appointment.date}",
#                 link=reverse('DurielEyeApp:appointment_list'),
#                 clinic_id=clinic_id,
#                 object_id=str(appointment.id),
#                 app_name='eye'
#             )

#         log_action(
#             self.request,
#             'CREATE',
#             appointment,
#             details=f"Created eye appointment for {appointment.patient.full_name} on {appointment.date}"
#         )

#         messages.success(self.request, "Appointment scheduled successfully!")
#         return redirect(self.success_url)




class EyeAppointmentCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = EyeAppointment
    form_class = EyeAppointmentForm
    template_name = 'eye/appointments/appointment_form.html'
    success_url = reverse_lazy('DurielEyeApp:appointment_list')

    def test_func(self):
        return self.request.user.role in ['ADMIN', 'DOCTOR', 'RECEPTIONIST', 'OPTOMETRIST']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['clinic_id'] = self.request.session.get('clinic_id')
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Limit provider choices to staff in the same clinic
        clinic_id = self.request.session.get('clinic_id')
        if clinic_id:
            form.fields['provider'].queryset = CustomUser.objects.filter(
                clinic__id=clinic_id,
                is_active=True,
                role__in=['DOCTOR', 'OPTOMETRIST', 'ADMIN']
            ).order_by('first_name', 'last_name')
        return form

    def form_valid(self, form):
        clinic_id = self.request.session.get('clinic_id')
        if not clinic_id:
            messages.error(self.request, "No clinic selected")
            return redirect('core:select_clinic')

        # Set clinic and save appointment
        form.instance.clinic_id = clinic_id
        form.instance.payment_type = form.cleaned_data.get('payment_type', 'SELF')  # Add this line
        appointment = form.save()

        # Create notification for staff in the same clinic
        staff_users = CustomUser.objects.filter(
            clinic__id=clinic_id,
            is_active=True
        )

        for user in staff_users:
            Notification.objects.create(
                user=user,
                message=f"New eye appointment with {appointment.patient.full_name} on {appointment.date}",
                link=reverse('DurielEyeApp:appointment_list'),
                clinic_id=clinic_id,
                object_id=str(appointment.id),
                app_name='eye'
            )

        # Also notify the provider if they're not the one creating the appointment
        if appointment.provider != self.request.user:
            Notification.objects.create(
                user=appointment.provider,
                message=f"You have a new appointment with {appointment.patient.full_name} on {appointment.date}",
                link=reverse('DurielEyeApp:appointment_list'),
                clinic_id=clinic_id,
                object_id=str(appointment.id),
                app_name='eye'
            )

        log_action(
            self.request,
            'CREATE',
            appointment,
            details=f"Created eye appointment for {appointment.patient.full_name} on {appointment.date}"
        )

        messages.success(self.request, "Appointment scheduled successfully!")
        return redirect(self.success_url)



@login_required
def eye_appointment_detail(request, pk):
    appointment = get_object_or_404(EyeAppointment, pk=pk)
    return render(request, 'eye/appointments/appointment_detail.html', {'appointment': appointment})




# def eye_appointment_update(request, appointment_id):
#     appointment = get_object_or_404(EyeAppointment, id=appointment_id)
#     clinic_id = request.session.get('clinic_id')

#     if request.method == "POST":
#         form = EyeAppointmentForm(request.POST, instance=appointment, clinic_id=clinic_id)
#         if form.is_valid():
#             form.save()
#             # ✅ Add logging
#             log_action(
#                 request,
#                 'UPDATE',
#                 appointment,
#                 details=f"Updated eye appointment for {appointment.patient.full_name} on {appointment.date}"
#             )
#             messages.success(request, "Eye appointment updated successfully.")
#             return redirect('DurielEyeApp:appointment_detail', pk=appointment.id)
#     else:
#         form = EyeAppointmentForm(instance=appointment, clinic_id=clinic_id)

#     return render(request, 'eye/appointments/appointment_form.html', {'form': form, 'appointment': appointment})



def eye_appointment_update(request, appointment_id):
    appointment = get_object_or_404(EyeAppointment, id=appointment_id)
    clinic_id = request.session.get('clinic_id')

    if request.method == "POST":
        form = EyeAppointmentForm(request.POST, instance=appointment, clinic_id=clinic_id)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.payment_type = form.cleaned_data.get('payment_type', appointment.payment_type)  # Add this line
            appointment.save()
            # ✅ Add logging
            log_action(
                request,
                'UPDATE',
                appointment,
                details=f"Updated eye appointment for {appointment.patient.full_name} on {appointment.date}"
            )
            messages.success(request, "Eye appointment updated successfully.")
            return redirect('DurielEyeApp:appointment_detail', pk=appointment.id)
    else:
        form = EyeAppointmentForm(instance=appointment, clinic_id=clinic_id)

    return render(request, 'eye/appointments/appointment_form.html', {'form': form, 'appointment': appointment})



def eye_appointment_delete(request, pk):
    appointment = get_object_or_404(EyeAppointment, id=pk)

    if request.method == "POST":
        # ✅ Add logging before deletion
        log_action(
            request,
            'DELETE',
            appointment,
            details=f"Deleted eye appointment for {appointment.patient.full_name} scheduled for {appointment.date}"
        )
        appointment.delete()
        messages.success(request, "Eye appointment deleted successfully.")
        return redirect('DurielEyeApp:appointment_list')

    return render(request, 'eye/appointments/appointment_delete.html', {'appointment': appointment})


def mark_eye_appointment_completed(request, pk):
    appointment = get_object_or_404(EyeAppointment, pk=pk)
    appointment.status = 'COMPLETED'
    appointment.save()
    # ✅ Add logging
    log_action(
        request,
        'UPDATE',
        appointment,
        details=f"Marked eye appointment as completed for {appointment.patient} on {appointment.date}"
    )
    messages.success(request, f"Appointment for {appointment.patient} marked as completed.")
    return redirect('DurielEyeApp:appointment_list')


def mark_eye_appointment_cancelled(request, appointment_id):
    appointment = get_object_or_404(EyeAppointment, id=appointment_id)
    appointment.status = 'CANCELLED'
    appointment.save()
    # ✅ Add logging
    log_action(
        request,
        'UPDATE',
        appointment,
        details=f"Cancelled eye appointment for {appointment.patient} scheduled for {appointment.date}"
    )
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
    exams = EyeExam.objects.all().order_by('-created_at')  # show all exams
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






# def delete_eye_medical_record(request, pk):
#     record = get_object_or_404(MedicalRecord, pk=pk)

#     if request.method == "POST":
#         record.delete()
#         return redirect('core:patient_detail', pk=record.patient.pk)

#     return render(request, 'eye/medical_records/delete_medical_record', {'object': record})

@login_required
def delete_eye_medical_record(request, record_id):
    record = get_object_or_404(EyeMedicalRecord, pk=record_id)

    if request.method == "POST":
        record.delete()
        return redirect('core:patient_detail', pk=record.patient.pk)

    return render(request, 'eye/medical_records/delete_eye_medical_record.html', {'object': record})




#-------------------------
#  Consultation
#-------------------------

@login_required
def begin_eye_consultation(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id)
    
    # Get latest appointment
    appointment = EyeAppointment.objects.filter(patient=patient).order_by('-date').first()
    
    clinic_id = request.session.get('clinic_id')
    if clinic_id and appointment:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        staff_users = User.objects.filter(clinic__id=clinic_id, is_active=True)
        
        # Get existing notifications for this appointment
        existing_notifications = Notification.objects.filter(
            clinic_id=clinic_id,
            object_id=str(appointment.id)
        ).values_list('user_id', flat=True)
        
        for user in staff_users:
            # Only create notification if one doesn't already exist for this user
            if user.id not in existing_notifications:
                Notification.objects.create(
                    user=user,
                    message=f"Consultation began with {appointment.patient.full_name} on {appointment.date}",
                    link=reverse('DurielEyeApp:appointment_list'),
                    clinic_id=clinic_id,
                    object_id=str(appointment.id),
                    app_name='eye'  # Add app_name to identify the source
                )

    context = {
        'patient': patient,
        'appointment': appointment
    }
    return render(request, 'eye/consultation/begin_consultation.html', context)





@login_required
def complete_eye_consultation(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id)
    
    appointment = EyeAppointment.objects.filter(patient=patient).order_by('-date').first()
    if appointment:
        appointment.status = 'COMPLETED'
        appointment.save()
        # ✅ Add logging
        log_action(
            request,
            'UPDATE',
            appointment,
            details=f"Completed consultation for {patient.full_name}"
        )
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
    template_name = 'eye/follow_up/schedule_follow_up.html'
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
    template_name = 'eye/follow_up/schedule_follow_up.html'
    

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
        followup.completed_at = timezone.now()
        followup.save()
        # ✅ Add logging
        log_action(
            request,
            'UPDATE',
            followup,
            details=f"Completed follow-up for {followup.patient.full_name}"
        )
        messages.success(request, f"Follow-up for {followup.patient.full_name} marked as completed.")
    else:
        messages.info(request, "Follow-up is already completed.")

    return redirect('DurielEyeApp:followup_list')


# --------------------
# Notifications
# --------------------
# @login_required
# def mark_eye_notification_read(request, pk):
#     clinic_id = request.session.get('clinic_id')
#     notification = get_object_or_404(EyeNotification, pk=pk, clinic_id=clinic_id)
#     if notification.user == request.user:
#         notification.is_read = True
#         notification.save()
#     elif notification.user is None:
#         EyeNotificationRead.objects.get_or_create(user=request.user, notification=notification)
#     return redirect(request.META.get('HTTP_REFERER', 'DurielEyeApp:dashboard'))


# @login_required
# def clear_eye_notifications(request):
#     clinic_id = request.session.get('clinic_id')
#     request.user.eye_notifications.filter(clinic_id=clinic_id).delete()
#     unread_globals = EyeNotification.objects.filter(user__isnull=True, clinic_id=clinic_id).exclude(
#         id__in=EyeNotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
#     )
#     EyeNotificationRead.objects.bulk_create(
#         [EyeNotificationRead(user=request.user, notification=n) for n in unread_globals],
#         ignore_conflicts=True
#     )
#     messages.success(request, "Notifications cleared")
#     return redirect(request.META.get('HTTP_REFERER', 'DurielEyeApp:dashboard'))


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
    
    
    
    
from django.core.mail import send_mail
from datetime import date
from django.urls import reverse
from django.conf import settings
from core.models import Notification, Patient


def check_birthdays(clinic_id=None):
    today = date.today()
    patients = Patient.objects.filter(
        date_of_birth__month=today.month,
        date_of_birth__day=today.day
    )
    if clinic_id:
        patients = patients.filter(clinic_id=clinic_id)

    for patient in patients:
        # Ensure we don't send duplicate notifications/emails per patient per day
        already_sent = Notification.objects.filter(
            object_id=str(patient.pk),
            clinic_id=patient.clinic_id,
            created_at__date=today,
            app_name='core'
        ).exists()

        if not already_sent:
            # ✅ Create notifications for staff
            staff_users = patient.clinic.staff.all() if hasattr(patient.clinic, 'staff') else []
            for user in staff_users:
                Notification.objects.create(
                    user=user,
                    message=f"Today is {patient.full_name}'s birthday!",
                    link=reverse('core:patient_detail', kwargs={'pk': patient.patient_id}),
                    clinic_id=patient.clinic_id,
                    object_id=str(patient.pk),
                    app_name='core'
                )

            # ✅ Send email to patient if email exists
            if getattr(patient, 'email', None):
                clinic_name = patient.clinic.name if patient.clinic else "Your Clinic"
                try:
                    send_mail(
                        'Happy Birthday!',
                        f'Dear {patient.full_name},\n\nHappy Birthday from {clinic_name}!',
                        settings.DEFAULT_FROM_EMAIL,
                        [patient.email],
                        fail_silently=False
                    )
                    # Log a notification (global) that email was sent
                    Notification.objects.create(
                        user=None,
                        message=f"Birthday email sent to {patient.full_name}",
                        clinic_id=patient.clinic_id,
                        object_id=str(patient.pk),
                        app_name='core'
                    )
                except Exception as e:
                    print(f"Error sending birthday email: {str(e)}")

