# DurielEyeApp/views.py

from datetime import date, timedelta, datetime, time
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Q, Count, Sum, Value, DecimalField, Exists, OuterRef
from django.contrib.contenttypes.models import ContentType
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView
from django.http import JsonResponse, HttpResponse
from django.utils.html import escape
from django.utils.timezone import make_aware
from django.utils.dateparse import parse_date, parse_time
from django.views.decorators.http import require_POST
from django.conf import settings  # ADD THIS IMPORT
from core.utils import ensure_appointment_consultation_charge, get_or_create_encounter_for_appointment, notify_role_handoff
from core.reporting import (
    build_clinic_report_context,
    queue_report_export,
    recent_report_jobs,
)

from core.models import Patient, Billing, BillingLineItem, CustomUser, Notification, NotificationRead, PatientEncounter, Prescription
from DurielMedicApp.models import Vitals
from .models import EyeAppointment, EyeMedicalRecord, EyeFollowUp, EyeExam, OpticalProduct, OpticalDispense, OpticalStockMovement, OpticalPrescriptionRequest
from .forms import EyeAppointmentForm, EyeMedicalRecordForm, EyeFollowUpForm, EyeExamForm, OpticalProductForm, OpticalDispenseForm, OpticalPrescriptionRequestNoteForm
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
from core.utils import log_action, notify_roles, notify_user_db, ensure_billing_line_item, appointment_billing_filter
from core.decorators import clinic_selected_required
from django.db.models import Prefetch
from django.utils import timezone
from core.decorators import role_required
from django.db import models


def _sync_optical_prescription_request(exam, actor):
    has_optical_request = (
        exam.frame_prescribed or exam.lens_prescribed or
        bool(exam.frame_product) or bool(exam.lens_product) or
        bool(exam.frame_prescription) or bool(exam.lens_prescription)
    )
    if not has_optical_request:
        return None

    request_obj, _ = OpticalPrescriptionRequest.objects.update_or_create(
        eye_exam=exam,
        defaults={
            'patient': exam.patient,
            'clinic': exam.patient.clinic,
            'appointment': exam.appointment,
            'frame_product': exam.frame_product,
            'frame_prescription': (
                exam.frame_prescription or
                (exam.frame_product.display_name if exam.frame_product else '')
            ) if exam.frame_prescribed or exam.frame_product or exam.frame_prescription else '',
            'lens_product': exam.lens_product,
            'lens_prescription': (
                exam.lens_prescription or
                (exam.lens_product.display_name if exam.lens_product else '')
            ) if exam.lens_prescribed or exam.lens_product or exam.lens_prescription else '',
            'prescribed_by': actor,
        },
    )
    return request_obj


def _active_eye_appointment_for_patient(patient, clinic):
    return EyeAppointment.objects.filter(
        patient=patient,
        clinic=clinic,
        status='SCHEDULED',
    ).order_by('-date', '-start_time').first()


def _sync_optical_dispense_to_billing(dispense, appointment=None, actor=None):
    if not dispense or not dispense.unit_price:
        return None

    encounter = None
    if appointment:
        encounter = get_or_create_encounter_for_appointment(appointment, actor)
        if dispense.appointment_id != appointment.pk or dispense.encounter_id != getattr(encounter, 'pk', None):
            dispense.appointment = appointment
            dispense.encounter = encounter
            dispense.save(update_fields=['appointment', 'encounter'])

    source_ct = ContentType.objects.get_for_model(dispense)
    existing = BillingLineItem.objects.filter(
        clinic=dispense.clinic,
        patient=dispense.patient,
        source_type='OPTICAL',
        source_content_type=source_ct,
        source_object_id=str(dispense.pk),
        status__in=['DRAFT', 'APPROVED'],
    ).first()
    if existing and appointment:
        for field, value in appointment_billing_filter(appointment).items():
            setattr(existing, field, value)
        existing.encounter = encounter
        existing.quantity = dispense.quantity
        existing.unit_price = dispense.unit_price
        existing.description = f"Optical: {dispense.product.display_name} x{dispense.quantity}"[:255]
        existing.save(update_fields=[
            'appointment_content_type', 'appointment_object_id', 'encounter',
            'quantity', 'unit_price', 'description', 'total_amount', 'updated_at',
        ])
        if existing.status == 'DRAFT':
            existing.approve(actor)
        return existing

    return ensure_billing_line_item(
        clinic=dispense.clinic,
        patient=dispense.patient,
        appointment=appointment,
        encounter=encounter,
        source_obj=dispense,
        source_type='OPTICAL',
        description=f"Optical: {dispense.product.display_name} x{dispense.quantity}",
        quantity=dispense.quantity,
        unit_price=dispense.unit_price,
        created_by=actor,
        auto_approve=True,
    )


def _dispense_prescribed_optical_products(optical_request, actor):
    appointment = optical_request.appointment or _active_eye_appointment_for_patient(
        optical_request.patient,
        optical_request.clinic,
    )
    created = []
    skipped = []
    for product in [optical_request.frame_product, optical_request.lens_product]:
        if not product or not product.selling_price:
            continue
        dispense, was_created = OpticalDispense.objects.get_or_create(
            patient=optical_request.patient,
            clinic=optical_request.clinic,
            appointment=appointment,
            eye_exam=optical_request.eye_exam,
            product=product,
            defaults={
                'encounter': get_or_create_encounter_for_appointment(appointment, actor) if appointment else None,
                'quantity': 1,
                'unit_price': product.selling_price or Decimal('0.00'),
                'notes': optical_request.optician_note or '',
                'dispensed_by': actor,
            },
        )
        if not was_created:
            dispense.unit_price = product.selling_price or Decimal('0.00')
            if appointment and not dispense.appointment_id:
                dispense.appointment = appointment
                dispense.encounter = get_or_create_encounter_for_appointment(appointment, actor)
            if actor and not dispense.dispensed_by_id:
                dispense.dispensed_by = actor
            dispense.save(update_fields=['appointment', 'encounter', 'unit_price', 'dispensed_by'])
        result = dispense.deduct_stock()
        if result is False:
            if was_created:
                dispense.delete()
            skipped.append(product)
            continue
        _sync_optical_dispense_to_billing(dispense, appointment, actor)
        created.append(dispense)
    return created, skipped






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
    return redirect('core:clinic_dashboard')
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
    
    recent_patients = Patient.objects.filter(
        clinic_id=clinic_id
    ).prefetch_related(
        Prefetch(
            'eye_appointments',
            queryset=EyeAppointment.objects.order_by('-date', '-start_time'),
            to_attr='ordered_eye_appointments'
        )
    ).order_by('-created_at')[:10]
    
    for patient in recent_patients:
        patient.last_appointment = patient.ordered_eye_appointments[0] if patient.ordered_eye_appointments else None
    
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
class EyeAppointmentListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = EyeAppointment
    template_name = 'eye/appointments/appointment_list.html'
    context_object_name = 'appointments'
    paginate_by = 10

    def test_func(self):
        return self.request.user.role in ['ADMIN', 'DOCTOR', 'OPTOMETRIST', 'RECEPTIONIST', 'NURSE']

    def get_queryset(self):
        clinic_id = self.request.session.get('clinic_id')
        appointment_type = ContentType.objects.get_for_model(EyeAppointment)
        qs = EyeAppointment.objects.filter(clinic_id=clinic_id).annotate(
            has_vitals=Exists(
                Vitals.objects.filter(
                    appointment_content_type=appointment_type,
                    appointment_object_id=OuterRef('pk'),
                )
            )
        )
        date_filter = self.request.GET.get('date', '')
        if date_filter:
            qs = qs.filter(date=date_filter)
        user = self.request.user
        if user.role in ['DOCTOR', 'OPTOMETRIST']:
            qs = qs.filter(provider=user)
        elif user.role not in ['ADMIN', 'RECEPTIONIST', 'NURSE']:
            qs = qs.filter(Q(provider=user) | Q(patient__created_by=user))
        today = timezone.localdate()
        qs = qs.annotate(
            day_bucket=models.Case(
                models.When(date=today, then=Value(0)),
                models.When(date__gt=today, then=Value(1)),
                default=Value(2),
                output_field=models.IntegerField(),
            )
        )
        return qs.order_by('day_bucket', 'date', 'start_time')


@login_required
@role_required('DOCTOR', 'OPTOMETRIST')
def today_appointment_count(request):
    clinic_id = request.session.get('clinic_id')
    if not clinic_id:
        return JsonResponse({'count': 0})

    today = timezone.localdate()
    count = EyeAppointment.objects.filter(
        clinic_id=clinic_id,
        date=today,
        status='SCHEDULED',
        provider=request.user,
    ).exclude(
        patient__status__in=['IN_CONSULTATION', 'CONSULTATION_COMPLETE']
    ).count()

    return JsonResponse({'count': count})





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

    def dispatch(self, request, *args, **kwargs):
        if not request.session.get('clinic_id'):
            messages.error(request, "No clinic selected")
            return redirect('core:select_clinic')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['clinic_id'] = self.request.session.get('clinic_id')
        return kwargs

    def form_valid(self, form):
        clinic_id = self.request.session.get('clinic_id')
        if not clinic_id:
            messages.error(self.request, "No clinic selected")
            return redirect('core:select_clinic')

        # Set clinic and save appointment
        form.instance.clinic_id = clinic_id
        form.instance.payment_type = form.cleaned_data.get('payment_type', 'SELF')  # Add this line
        appointment = form.save()

        patient = getattr(appointment, "patient", None)
        if patient and patient.status in ["DISCHARGED", "FOLLOW_UP_COMPLETE"]:
            patient.status = "REGISTERED"
            patient.save(update_fields=["status"])

        notify_role_handoff(
            appointment.clinic,
            ['DOCTOR', 'OPTOMETRIST'],
            f"New eye appointment for {appointment.patient.full_name} on {appointment.date}",
            link=reverse('DurielEyeApp:appointment_detail', kwargs={'pk': appointment.pk}),
            app_name='eye',
            object_id=appointment.pk,
            actor=self.request.user,
            provider=appointment.provider,
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
@clinic_selected_required
def eye_appointment_detail(request, pk):
    appointment = get_object_or_404(EyeAppointment, pk=pk, clinic_id=request.session.get('clinic_id'))
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



@login_required
@clinic_selected_required
@role_required('ADMIN', 'DOCTOR', 'OPTOMETRIST', 'RECEPTIONIST', 'NURSE')
def eye_appointment_update(request, appointment_id):
    clinic_id = request.session.get('clinic_id')
    appointment = get_object_or_404(EyeAppointment, id=appointment_id, clinic_id=clinic_id)

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
        messages.error(request, 'The appointment was not updated. Please correct the highlighted fields.')
    else:
        form = EyeAppointmentForm(instance=appointment, clinic_id=clinic_id)

    return render(request, 'eye/appointments/appointment_form.html', {'form': form, 'appointment': appointment})



@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST', 'NURSE')
def eye_appointment_delete(request, pk):
    appointment = get_object_or_404(EyeAppointment, id=pk, clinic_id=request.session.get('clinic_id'))

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


@login_required
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST', 'NURSE')
def mark_eye_appointment_completed(request, pk):
    appointment = get_object_or_404(EyeAppointment, pk=pk, clinic_id=request.session.get('clinic_id'))
    if appointment.status != 'COMPLETED':
        appointment.status = 'COMPLETED'
        appointment.save(update_fields=['status'])
        ensure_appointment_consultation_charge(appointment, request.user, description='Consultation')
        log_action(
            request,
            'UPDATE',
            appointment,
            details=f"Marked eye appointment as completed for {appointment.patient} on {appointment.date}"
        )
        notify_role_handoff(
            appointment.clinic,
            ['ADMIN', 'RECEPTIONIST', 'NURSE', 'DOCTOR', 'OPTOMETRIST'],
            f"Eye consultation completed for {appointment.patient.full_name}. Billing/review pending.",
            link=f"{reverse('core:create_bill')}?patient={appointment.patient.patient_id}&appointment_id={appointment.pk}&appointment_type=eye",
            app_name='eye',
            object_id=appointment.pk,
            actor=request.user,
            provider=appointment.provider,
        )
        messages.success(request, f"Consultation for {appointment.patient.full_name} completed.")
    else:
        messages.info(request, "Consultation is already completed.")
    return redirect('DurielEyeApp:appointment_detail', pk=appointment.pk)


@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST', 'NURSE')
@require_POST
def mark_eye_appointment_cancelled(request, pk):
    appointment = get_object_or_404(EyeAppointment, id=pk, clinic_id=request.session.get('clinic_id'))
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
    return redirect('DurielEyeApp:appointment_list')



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
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST')
def record_eye_exam(request, appointment_id):
    clinic_id = request.session.get('clinic_id')
    appointment = get_object_or_404(EyeAppointment, pk=appointment_id, clinic_id=clinic_id)

    if request.method == 'POST':
        form = EyeExamForm(request.POST, clinic_id=clinic_id)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.patient = appointment.patient  # assign the patient
            exam.appointment = appointment      # ✅ assign appointment
            exam.encounter = get_or_create_encounter_for_appointment(appointment, request.user)
            exam.created_by = request.user      # assign who created it
            exam.save()
            optical_request = _sync_optical_prescription_request(exam, request.user)
            if optical_request:
                notify_role_handoff(
                    appointment.clinic,
                    ['OPTICIAN'],
                    f"Optical prescription for {exam.patient.full_name}: {optical_request.requested_items}.",
                    link=reverse('DurielEyeApp:optical_prescription_queue'),
                    app_name='eye',
                    object_id=optical_request.pk,
                    actor=request.user,
                )
            messages.success(request, f"Eye exam for {exam.patient.full_name} recorded successfully.")
            # return redirect('DurielEyeApp:appointment_detail', pk=appointment.pk)
            log_action(request, 'CREATE', exam, details=f"Recorded eye exam for {exam.patient.full_name}")
            return redirect('DurielEyeApp:begin_consultation', patient_id=appointment.patient.patient_id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = EyeExamForm(clinic_id=clinic_id)

    context = {
        'form': form,
        'appointment': appointment
    }
    exams = EyeExam.objects.all().order_by('-created_at')  # show all exams
    return render(request, 'eye/exams/record_exam.html', context)



@login_required
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST')
def view_eye_exam(request, exam_id):
    exam = get_object_or_404(
        EyeExam.objects.select_related('patient', 'appointment', 'created_by', 'frame_product', 'lens_product'),
        pk=exam_id,
        patient__clinic=request.clinic,
    )
    return render(request, 'eye/exams/view_eye_exam.html', {'exam': exam})


@login_required
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST')
def edit_eye_exam(request, exam_id):
    clinic_id = request.session.get('clinic_id')
    exam = get_object_or_404(EyeExam, pk=exam_id, patient__clinic_id=clinic_id)

    if request.method == 'POST':
        form = EyeExamForm(request.POST, instance=exam, clinic_id=clinic_id)
        if form.is_valid():
            exam = form.save()
            optical_request = _sync_optical_prescription_request(exam, request.user)
            if optical_request:
                notify_role_handoff(
                    exam.patient.clinic,
                    ['OPTICIAN'],
                    f"Optical prescription updated for {exam.patient.full_name}: {optical_request.requested_items}.",
                    link=reverse('DurielEyeApp:optical_prescription_queue'),
                    app_name='eye',
                    object_id=optical_request.pk,
                    actor=request.user,
                )
            log_action(request, 'UPDATE', exam, details=f"Updated eye exam for {exam.patient.full_name}")
            messages.success(request, f"Eye exam for {exam.patient.full_name} updated successfully.")
            return redirect('DurielEyeApp:begin_consultation', patient_id=exam.patient.patient_id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = EyeExamForm(instance=exam, clinic_id=clinic_id)

    return render(request, 'eye/exams/edit_eye_exam.html', {'form': form, 'exam': exam})







@login_required
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST')
def delete_eye_exam(request, exam_id):
    record = get_object_or_404(EyeExam, pk=exam_id, patient__clinic_id=request.session.get('clinic_id'))

    if request.method == "POST":
        record.delete()
        return redirect('core:patient_detail', pk=record.patient.pk)

    return render(request, 'eye/exams/delete_eye_exam.html', {'object': record})




# --------------------
# Medical Records
# --------------------
@login_required
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST')
def view_eye_medical_record(request, record_id):
    record = get_object_or_404(EyeMedicalRecord, pk=record_id, clinic=request.clinic)
    return render(request, 'eye/medical_records/view_record.html', {'record': record})


@login_required
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST')
def add_eye_medical_record(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id, clinic=request.clinic, clinic__clinic_type='EYE')

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




@login_required
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST')
def edit_eye_medical_record(request, record_id):
    record = get_object_or_404(EyeMedicalRecord, id=record_id, clinic=request.clinic)
    
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
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST')
def delete_eye_medical_record(request, record_id):
    record = get_object_or_404(EyeMedicalRecord, pk=record_id, clinic=request.clinic)

    if request.method == "POST":
        record.delete()
        return redirect('core:patient_detail', pk=record.patient.pk)

    return render(request, 'eye/medical_records/delete_eye_medical_record.html', {'object': record})


@login_required
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST')
def export_eye_patient_record_pdf(request, patient_id):
    """Export an eye patient record including eye exams and prescriptions."""
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    patient = get_object_or_404(Patient, pk=patient_id, clinic=request.clinic, clinic__clinic_type='EYE')
    eye_appointment_type = ContentType.objects.get_for_model(EyeAppointment)
    encounter_id = request.GET.get('encounter_id')
    appointment_id = request.GET.get('appointment_id')
    encounter_filter = PatientEncounter.objects.filter(
        patient=patient,
        clinic=request.clinic,
        appointment_content_type=eye_appointment_type,
    )
    if encounter_id:
        encounter_filter = encounter_filter.filter(pk=encounter_id)
    elif appointment_id:
        encounter_filter = encounter_filter.filter(appointment_object_id=appointment_id)
        if not encounter_filter.exists():
            appointment = get_object_or_404(EyeAppointment, pk=appointment_id, patient=patient, clinic=request.clinic)
            get_or_create_encounter_for_appointment(appointment, request.user)
            encounter_filter = PatientEncounter.objects.filter(
                patient=patient,
                clinic=request.clinic,
                appointment_content_type=eye_appointment_type,
                appointment_object_id=appointment_id,
            )
    encounters = list(encounter_filter.select_related('provider', 'appointment_content_type').order_by('-started_at'))
    if not encounter_id and not appointment_id:
        encounters = encounters[:1]
    eye_records = list(EyeMedicalRecord.objects.filter(patient=patient, clinic=request.clinic).select_related('created_by').order_by('-created_at'))
    eye_exams = list(EyeExam.objects.filter(patient=patient).select_related(
        'appointment', 'encounter', 'created_by', 'frame_product', 'lens_product'
    ).order_by('-created_at'))
    prescriptions = list(Prescription.objects.filter(patient=patient, clinic=request.clinic).select_related(
        'clinic_medication', 'prescribed_by', 'encounter'
    ).order_by('-date_prescribed'))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('EyeRecordTitle', parent=styles['Heading1'], fontSize=18, spaceAfter=14, textColor=colors.HexColor('#1f2937'))
    heading_style = ParagraphStyle('EyeRecordHeading', parent=styles['Heading2'], fontSize=12, spaceBefore=12, spaceAfter=7, textColor=colors.HexColor('#1d4ed8'))
    body_style = ParagraphStyle('EyeRecordBody', parent=styles['Normal'], fontSize=9.5, leading=13, spaceAfter=6)

    def add_text(title, content):
        if content:
            story.append(Paragraph(escape(title), heading_style))
            story.append(Paragraph(escape(str(content)).replace('\n', '<br/>'), body_style))

    story = [
        Paragraph('Eye Encounter Medical Record', title_style),
        Paragraph(f"<b>Patient:</b> {escape(patient.full_name)}", body_style),
        Paragraph(f"<b>Patient ID:</b> {escape(patient.patient_id)}", body_style),
        Paragraph(f"<b>Clinic:</b> {escape(request.clinic.name)}", body_style),
        Paragraph(f"<b>Exported:</b> {timezone.now().strftime('%B %d, %Y %I:%M %p')}", body_style),
        Spacer(1, 0.2 * inch),
    ]

    def add_exam(exam):
        story.append(Paragraph(f"<b>Exam Date:</b> {exam.created_at.strftime('%B %d, %Y')}", body_style))
        story.append(Paragraph(
            f"<b>Left Eye:</b> VA {escape(exam.visual_acuity_left or 'Not recorded')}; "
            f"IOP {escape(str(exam.intraocular_pressure_left or 'Not recorded'))}; "
            f"Rx {escape(exam.final_prescription_left or exam.refraction_left or 'Not recorded')}",
            body_style,
        ))
        story.append(Paragraph(
            f"<b>Right Eye:</b> VA {escape(exam.visual_acuity_right or 'Not recorded')}; "
            f"IOP {escape(str(exam.intraocular_pressure_right or 'Not recorded'))}; "
            f"Rx {escape(exam.final_prescription_right or exam.refraction_right or 'Not recorded')}",
            body_style,
        ))
        add_text('Chief Complaint', exam.chief_complaint)
        add_text('Diagnosis', exam.diagnosis)
        add_text('Treatment Plan', exam.treatment_plan)
        if exam.frame_product or exam.frame_prescription:
            frame_text = exam.frame_prescription or exam.frame_product.display_name
            add_text('Frame Prescription', frame_text)
        if exam.lens_product or exam.lens_prescription:
            lens_text = exam.lens_prescription or exam.lens_product.display_name
            add_text('Lens Prescription', lens_text)
        add_text('Follow-up Plan', exam.follow_up_plan)

    def add_prescription(prescription):
        story.append(Paragraph(
            f"<b>{escape(prescription.medication_name or 'Medication')}</b> - "
            f"{escape(prescription.dosage)}; {escape(prescription.frequency)}; "
            f"{escape(prescription.duration)}; Qty {prescription.quantity_prescribed}",
            body_style,
        ))
        add_text('Instructions', prescription.instructions)

    used_exam_ids = set()
    used_prescription_ids = set()
    story.append(Paragraph('Encounters', heading_style))
    if encounters:
        for encounter in encounters:
            appointment = encounter.appointment
            appointment_id = getattr(appointment, 'pk', None)
            visit_exams = [
                exam for exam in eye_exams
                if exam.encounter_id == encounter.pk or (appointment_id and exam.appointment_id == appointment_id)
            ]
            visit_prescriptions = [
                prescription for prescription in prescriptions
                if prescription.encounter_id == encounter.pk
            ]
            used_exam_ids.update(exam.pk for exam in visit_exams)
            used_prescription_ids.update(prescription.pk for prescription in visit_prescriptions)

            story.append(Paragraph(
                f"<b>Encounter:</b> {escape(encounter.get_encounter_type_display())} "
                f"| {escape(encounter.get_status_display())} "
                f"| Started {encounter.started_at.strftime('%B %d, %Y %I:%M %p')}",
                body_style,
            ))
            if encounter.provider:
                story.append(Paragraph(
                    f"<b>Provider:</b> {escape(encounter.provider.get_full_name() or encounter.provider.username)}",
                    body_style,
                ))
            if appointment:
                story.append(Paragraph(
                    f"<b>Appointment:</b> {appointment.date.strftime('%B %d, %Y')} at {appointment.start_time.strftime('%I:%M %p')} "
                    f"| Status: {escape(appointment.get_status_display())}",
                    body_style,
                ))
                add_text('Reason', appointment.reason)

            if visit_exams:
                story.append(Paragraph('Eye Exam', heading_style))
                for exam in visit_exams:
                    add_exam(exam)
            else:
                story.append(Paragraph('No eye exam recorded for this visit.', body_style))

            if visit_prescriptions:
                story.append(Paragraph('Prescriptions', heading_style))
                for prescription in visit_prescriptions:
                    add_prescription(prescription)
            else:
                story.append(Paragraph('No prescriptions linked to this encounter.', body_style))

            story.append(Spacer(1, 0.18 * inch))
    else:
        story.append(Paragraph('No eye encounters recorded.', body_style))

    include_unlinked = not encounters
    unlinked_exams = [exam for exam in eye_exams if exam.pk not in used_exam_ids]
    unlinked_prescriptions = [prescription for prescription in prescriptions if prescription.pk not in used_prescription_ids]
    if include_unlinked and (unlinked_exams or unlinked_prescriptions or eye_records):
        story.append(Paragraph('Unlinked / Historical Records', heading_style))
        if unlinked_exams:
            story.append(Paragraph('Eye Exams Without Appointment/Encounter Match', heading_style))
            for exam in unlinked_exams:
                add_exam(exam)
                story.append(Spacer(1, 0.12 * inch))
        if unlinked_prescriptions:
            story.append(Paragraph('Prescriptions Without Appointment/Encounter Match', heading_style))
            for prescription in unlinked_prescriptions:
                add_prescription(prescription)
        if eye_records:
            story.append(Paragraph('Additional Eye Medical Records', heading_style))
            for record in eye_records:
                story.append(Paragraph(
                    f"<b>{escape(record.get_record_type_display())}</b> - {escape(record.title)} "
                    f"({record.created_at.strftime('%B %d, %Y')})",
                    body_style,
                ))
                add_text('Description', record.description)

    log_action(request, 'UPDATE', patient, details=f"Exported eye encounter record PDF for {patient.full_name}")
    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    suffix = f"encounter_{encounters[0].pk}" if encounters else "unlinked"
    response['Content-Disposition'] = f'attachment; filename="eye_record_{patient.patient_id}_{suffix}.pdf"'
    return response




#-------------------------
#  Consultation
#-------------------------

@login_required
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST')
def begin_eye_consultation(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic=request.clinic)

    if patient.status != 'IN_CONSULTATION':
        patient.status = 'IN_CONSULTATION'
        patient.save(update_fields=['status'])
    
    # Get latest appointment and any vitals recorded for that appointment.
    appointment = EyeAppointment.objects.filter(
        patient=patient,
        clinic=request.clinic,
    ).order_by('-date', '-start_time').first()
    vitals = None
    if appointment:
        appointment_type = ContentType.objects.get_for_model(EyeAppointment)
        vitals = Vitals.objects.filter(
            appointment_content_type=appointment_type,
            appointment_object_id=appointment.pk,
        ).order_by('-id').first()

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
        'appointment': appointment,
        'vitals': vitals,
    }
    return render(request, 'eye/consultation/begin_consultation.html', context)





@login_required
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST')
@require_POST
def complete_eye_consultation(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic=request.clinic)
    
    appointment = _active_eye_appointment_for_patient(patient, request.clinic)
    if appointment:
        ensure_appointment_consultation_charge(appointment, request.user, description='Consultation')
        optical_dispenses = OpticalDispense.objects.filter(
            patient=patient,
            clinic=request.clinic,
            unit_price__gt=0,
        ).filter(
            Q(appointment=appointment) |
            Q(appointment__isnull=True, dispensed_at__date__gte=appointment.date)
        )
        synced_optical_items = [
            item for item in (
                _sync_optical_dispense_to_billing(dispense, appointment, request.user)
                for dispense in optical_dispenses
            )
            if item
        ]
        appointment.status = 'COMPLETED'
        appointment.save()
        # ✅ Add logging
        log_action(
            request,
            'UPDATE',
            appointment,
            details=(
                f"Completed consultation for {patient.full_name}. "
                f"Optical billing items synced: {len(synced_optical_items)}"
            )
        )
        notify_roles(
            patient.clinic,
            ['ADMIN', 'RECEPTIONIST', 'PHARMACIST'],
            f"Eye consultation completed for {patient.full_name}. Review billing and prescriptions.",
            link=reverse('core:patient_detail', kwargs={'pk': patient.patient_id}),
            app_name='eye',
            object_id=patient.patient_id,
            exclude_user=request.user,
        )
        messages.success(request, f"Consultation for {patient.full_name} marked as completed.")
    else:
        messages.warning(request, f"No active appointment found for {patient.full_name}.")

    return redirect('core:patient_detail', pk=patient.pk)


# --------------------
# Follow-ups
# --------------------
class EyeFollowUpListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = EyeFollowUp
    template_name = 'eye/follow_up/followup_list.html'
    context_object_name = 'followups'
    paginate_by = 10

    def test_func(self):
        return self.request.user.role in ['ADMIN', 'DOCTOR', 'OPTOMETRIST', 'RECEPTIONIST', 'NURSE']

    def get_queryset(self):
        return EyeFollowUp.objects.filter(clinic_id=self.request.session.get('clinic_id')).order_by('scheduled_date', 'scheduled_time')


class EyeFollowUpCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = EyeFollowUp
    form_class = EyeFollowUpForm
    template_name = 'eye/follow_up/schedule_follow_up.html'
    success_url = reverse_lazy('DurielEyeApp:followup_list')

    def test_func(self):
        return self.request.user.role in ['ADMIN', 'DOCTOR', 'OPTOMETRIST', 'RECEPTIONIST', 'NURSE']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['clinic_id'] = self.request.session.get('clinic_id')
        return kwargs

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



class EyeFollowUpUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = EyeFollowUp
    form_class = EyeFollowUpForm
    template_name = 'eye/follow_up/schedule_follow_up.html'

    def test_func(self):
        return self.request.user.role in ['ADMIN', 'DOCTOR', 'OPTOMETRIST', 'RECEPTIONIST', 'NURSE']

    def get_queryset(self):
        return EyeFollowUp.objects.filter(clinic_id=self.request.session.get('clinic_id'))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['clinic_id'] = self.request.session.get('clinic_id')
        return kwargs
    

@login_required
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST')
def schedule_eye_follow_up(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic=request.clinic, clinic__clinic_type='EYE')

    if request.method == "POST":
        form = EyeFollowUpForm(request.POST, clinic_id=patient.clinic_id)
        if form.is_valid():
            follow_up = form.save(commit=False)
            follow_up.patient = patient
            follow_up.clinic = patient.clinic
            follow_up.created_by = request.user
            follow_up.save()
            messages.success(request, f"Follow-up scheduled for {patient.full_name}.")
            return redirect('core:patient_detail', pk=patient.patient_id)
    else:
        form = EyeFollowUpForm(clinic_id=patient.clinic_id)

    return render(request, "eye/follow_up/schedule_follow_up.html", {
        "form": form,
        "patient": patient
    })


@require_POST
@login_required
@clinic_selected_required
@role_required('DOCTOR', 'OPTOMETRIST', 'NURSE')
def complete_eye_follow_up(request, pk):
    followup = get_object_or_404(EyeFollowUp, pk=pk, clinic=request.clinic)

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

# @login_required
# @user_passes_test(admin_check, login_url='login')
# def generate_eye_report(request):
#     clinic_id = request.session.get('clinic_id')
#     if not clinic_id:
#         messages.error(request, "No clinic selected. Please select a clinic first.")
#         return redirect('core:select_clinic')

#     # Default date range: last 30 days
#     end_date = timezone.now()
#     start_date = end_date - timedelta(days=30)

#     if request.method == 'POST':
#         start_date_str = request.POST.get('start_date')
#         end_date_str = request.POST.get('end_date')
#         report_type = request.POST.get('report_type')

#         if start_date_str and end_date_str:
#             start_date = make_aware(datetime.combine(datetime.strptime(start_date_str, '%Y-%m-%d'), time.min))
#             end_date = make_aware(datetime.combine(datetime.strptime(end_date_str, '%Y-%m-%d'), time.max))

#         # Route to correct report
#         if report_type == 'appointments':
#             return generate_eye_appointment_report(start_date, end_date, clinic_id)
#         elif report_type == 'patients':
#             return generate_eye_patient_report(start_date, end_date, clinic_id)
#         elif report_type == 'financial':
#             return generate_eye_financial_report(start_date, end_date, clinic_id)

#     # ✅ Appointment stats with status labels
#     try:
#         STATUS_LABELS = dict(EyeAppointment._meta.get_field('status').choices)

#         raw_stats = EyeAppointment.objects.filter(
#             clinic_id=clinic_id,
#             date__range=[start_date.date(), end_date.date()]
#         ).values('status').annotate(count=Count('id'))

#         appointment_stats = [
#             {
#                 'status': STATUS_LABELS.get(stat['status'], stat['status']),
#                 'count': stat['count']
#             }
#             for stat in raw_stats
#         ]

#         print(f"DEBUG: appointment_stats = {appointment_stats}")

#     except Exception as e:
#         appointment_stats = []
#         print(f"Appointment stats error: {e}")

#     # Patient stats
#     patient_stats = Patient.objects.filter(
#         clinic_id=clinic_id,
#         created_at__range=[start_date, end_date]
#     ).aggregate(total=Count('pk'))

#     # Financial stats
#     try:
#         financial_stats = Billing.objects.filter(
#             clinic_id=clinic_id,
#             service_date__range=[start_date.date(), end_date.date()]
#         ).aggregate(
#             total_amount=Sum('amount'),
#             total_paid=Sum('paid_amount')
#         )

#         if not financial_stats['total_amount']:
#             financial_stats['total_amount'] = 0
#         if not financial_stats['total_paid']:
#             financial_stats['total_paid'] = 0

#     except Exception as e:
#         financial_stats = {'total_amount': 0, 'total_paid': 0}
#         print(f"Financial stats error: {e}")

#     context = {
#         'start_date': start_date.date(),
#         'end_date': end_date.date(),
#         'appointment_stats': appointment_stats,
#         'patient_stats': patient_stats,
#         'financial_stats': financial_stats,
#     }

#     return render(request, 'eye/reports/generate_eye_report.html', context)


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
    start_date_str = request.GET.get('start_date') or request.POST.get('start_date')
    end_date_str = request.GET.get('end_date') or request.POST.get('end_date')
    if start_date_str and end_date_str:
        try:
            start_date = make_aware(datetime.combine(datetime.strptime(start_date_str, '%Y-%m-%d'), time.min))
            end_date = make_aware(datetime.combine(datetime.strptime(end_date_str, '%Y-%m-%d'), time.max))
        except ValueError:
            messages.error(request, "Invalid report date range.")

    if request.method == 'POST':
        report_type = request.POST.get('report_type')
        allowed_reports = {'appointments', 'patients', 'financial', 'prescriptions', 'consultations', 'optical_prescriptions'}
        if report_type in allowed_reports:
            queue_report_export(
                request,
                report_scope='eye',
                report_type=report_type,
                start_date=start_date,
                end_date=end_date,
                clinic_id=clinic_id,
            )
            messages.success(request, 'Report export queued. It will appear below when ready.')
            return redirect(f"{request.path}?start_date={start_date.date()}&end_date={end_date.date()}")

    optical_service_orders_count = OpticalPrescriptionRequest.objects.filter(
        clinic_id=clinic_id,
        created_at__range=[start_date, end_date],
    ).count()

    # Eye clinic uses the same rich analytics dashboard as General (shared helper
    # + shared reports/generate_report.html template).
    context = build_clinic_report_context(
        clinic_id,
        EyeAppointment,
        start_date,
        end_date,
        extra_operation_items=[
            {'label': 'Optical service orders', 'count': optical_service_orders_count},
        ],
        extra_export_items=[
            {'label': 'Export Optical Prescriptions CSV', 'report_type': 'optical_prescriptions'},
        ],
    )
    context['report_jobs'] = recent_report_jobs(request, clinic_id)
    return render(request, 'reports/generate_report.html', context)


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


# ============================================================
# Optical Lab (dispensary) — inventory + dispensing to billing
# ============================================================

OPTICAL_MANAGE_ROLES = ('OPTICIAN',)


@login_required
@clinic_selected_required
@role_required(*OPTICAL_MANAGE_ROLES)
def optical_product_list(request):
    """List optical inventory for the current eye clinic."""
    clinic = request.clinic
    products = OpticalProduct.objects.filter(clinic=clinic).order_by('name')

    search = request.GET.get('search', '').strip()
    type_filter = request.GET.get('product_type', '')
    stock_filter = request.GET.get('stock_status', '')

    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(brand__icontains=search) |
            Q(model_code__icontains=search)
        )
    if type_filter:
        products = products.filter(product_type=type_filter)
    if stock_filter == 'out_of_stock':
        products = products.filter(quantity_in_stock=0)
    elif stock_filter == 'low_stock':
        products = products.filter(
            quantity_in_stock__lte=models.F('minimum_stock_level'),
            quantity_in_stock__gt=0,
        )
    elif stock_filter == 'in_stock':
        products = products.filter(quantity_in_stock__gt=models.F('minimum_stock_level'))

    context = {
        'products': products,
        'search': search,
        'type_filter': type_filter,
        'stock_filter': stock_filter,
        'product_types': OpticalProduct.PRODUCT_TYPES,
        'clinic': clinic,
        'low_stock_count': OpticalProduct.objects.filter(
            clinic=clinic,
            quantity_in_stock__lte=models.F('minimum_stock_level'),
            quantity_in_stock__gt=0,
        ).count(),
        'pending_optical_requests': OpticalPrescriptionRequest.objects.filter(
            clinic=clinic,
            status__in=['PENDING', 'ACKNOWLEDGED', 'PROCESSED'],
        ).count(),
    }
    return render(request, 'eye/optical/product_list.html', context)


@login_required
@clinic_selected_required
@role_required(*OPTICAL_MANAGE_ROLES)
def optical_pending_count(request):
    count = OpticalPrescriptionRequest.objects.filter(
        clinic=request.clinic,
        status__in=['PENDING', 'ACKNOWLEDGED', 'PROCESSED'],
    ).count()
    return JsonResponse({'count': count})


@login_required
@clinic_selected_required
@role_required(*OPTICAL_MANAGE_ROLES)
def optical_prescription_queue(request):
    clinic = request.clinic
    status_filter = request.GET.get('status', '')
    requests = (OpticalPrescriptionRequest.objects
                .filter(clinic=clinic)
                .select_related('patient', 'appointment', 'eye_exam', 'frame_product', 'lens_product', 'prescribed_by',
                                'acknowledged_by', 'processed_by', 'dispensed_by'))
    if status_filter:
        requests = requests.filter(status=status_filter)
    return render(request, 'eye/optical/prescription_queue.html', {
        'requests': requests,
        'status_filter': status_filter,
        'statuses': OpticalPrescriptionRequest.STATUS_CHOICES,
        'clinic': clinic,
    })


@login_required
@clinic_selected_required
@role_required(*OPTICAL_MANAGE_ROLES)
@require_POST
def update_optical_prescription_status(request, pk, status):
    optical_request = get_object_or_404(OpticalPrescriptionRequest, pk=pk, clinic=request.clinic)
    valid_transitions = {
        'ACKNOWLEDGED': ('PENDING',),
        'PROCESSED': ('PENDING', 'ACKNOWLEDGED'),
        'DISPENSED': ('PENDING', 'ACKNOWLEDGED', 'PROCESSED'),
    }
    if status not in valid_transitions or optical_request.status not in valid_transitions[status]:
        messages.error(request, "This optical request cannot be moved to that status.")
        return redirect('DurielEyeApp:optical_prescription_queue')

    now = timezone.now()
    if status == 'ACKNOWLEDGED':
        optical_request.acknowledged_by = request.user
        optical_request.acknowledged_at = now
    elif status == 'PROCESSED':
        optical_request.processed_by = request.user
        optical_request.processed_at = now
    elif status == 'DISPENSED':
        optical_request.dispensed_by = request.user
        optical_request.dispensed_at = now
        created_dispenses, skipped_products = _dispense_prescribed_optical_products(optical_request, request.user)
        for product in skipped_products:
            messages.error(request, f"Insufficient stock to dispense {product.display_name}.")
        if skipped_products and not created_dispenses:
            return redirect('DurielEyeApp:optical_prescription_queue')
    optical_request.status = status
    optical_request.save()

    log_action(
        request,
        'UPDATE',
        optical_request,
        details=f"Marked optical request for {optical_request.patient.full_name} as {optical_request.get_status_display()}",
    )
    messages.success(request, f"Optical request marked as {optical_request.get_status_display()}.")
    if status == 'DISPENSED' and created_dispenses:
        messages.success(request, f"{len(created_dispenses)} optical item(s) added to billing.")
    return redirect('DurielEyeApp:optical_prescription_queue')


@login_required
@clinic_selected_required
@role_required(*OPTICAL_MANAGE_ROLES)
def edit_optical_prescription_note(request, pk):
    optical_request = get_object_or_404(OpticalPrescriptionRequest, pk=pk, clinic=request.clinic)
    if request.method == 'POST':
        form = OpticalPrescriptionRequestNoteForm(request.POST, instance=optical_request)
        if form.is_valid():
            form.save()
            log_action(request, 'UPDATE', optical_request,
                       details=f"Updated optician note for {optical_request.patient.full_name}")
            messages.success(request, "Optician note saved.")
            return redirect('DurielEyeApp:optical_prescription_queue')
    else:
        form = OpticalPrescriptionRequestNoteForm(instance=optical_request)
    return render(request, 'eye/optical/prescription_note_form.html', {
        'form': form,
        'optical_request': optical_request,
        'clinic': request.clinic,
    })


@login_required
@clinic_selected_required
@role_required(*OPTICAL_MANAGE_ROLES)
def add_optical_product(request):
    """Add a new optical product to inventory."""
    clinic = request.clinic
    if request.method == 'POST':
        form = OpticalProductForm(request.POST, clinic=clinic)
        if form.is_valid():
            product = form.save(commit=False)
            product.clinic = clinic
            product.added_by = request.user
            product.save()
            if product.quantity_in_stock > 0:
                OpticalStockMovement.objects.create(
                    product=product,
                    movement_type='IN',
                    quantity=product.quantity_in_stock,
                    previous_stock=0,
                    new_stock=product.quantity_in_stock,
                    created_by=request.user,
                    notes='Initial stock entry',
                )
            log_action(request, 'CREATE', product,
                       details=f"Added optical product: {product.display_name}")
            messages.success(request, f"Optical product '{product.display_name}' added.")
            return redirect('DurielEyeApp:optical_product_list')
    else:
        form = OpticalProductForm(clinic=clinic)
    return render(request, 'eye/optical/product_form.html',
                  {'form': form, 'clinic': clinic, 'title': 'Add Optical Product'})


@login_required
@clinic_selected_required
@role_required(*OPTICAL_MANAGE_ROLES)
def edit_optical_product(request, pk):
    """Edit an existing optical product; log a stock adjustment if quantity changes."""
    clinic = request.clinic
    product = get_object_or_404(OpticalProduct, pk=pk, clinic=clinic)
    old_stock = product.quantity_in_stock
    if request.method == 'POST':
        form = OpticalProductForm(request.POST, instance=product, clinic=clinic)
        if form.is_valid():
            product = form.save()
            if product.quantity_in_stock != old_stock:
                OpticalStockMovement.objects.create(
                    product=product,
                    movement_type='ADJUSTMENT',
                    quantity=product.quantity_in_stock - old_stock,
                    previous_stock=old_stock,
                    new_stock=product.quantity_in_stock,
                    created_by=request.user,
                    notes='Stock adjusted via edit',
                )
            log_action(request, 'UPDATE', product,
                       details=f"Updated optical product: {product.display_name}")
            messages.success(request, f"Optical product '{product.display_name}' updated.")
            return redirect('DurielEyeApp:optical_product_list')
    else:
        form = OpticalProductForm(instance=product, clinic=clinic)
    return render(request, 'eye/optical/product_form.html',
                  {'form': form, 'clinic': clinic, 'product': product, 'title': 'Edit Optical Product'})


@login_required
@clinic_selected_required
@role_required(*OPTICAL_MANAGE_ROLES)
def dispense_optical(request, pk):
    """Dispense an optical product to a patient: deduct stock and add to billing."""
    clinic = request.clinic
    product = get_object_or_404(OpticalProduct, pk=pk, clinic=clinic)

    if request.method == 'POST':
        form = OpticalDispenseForm(request.POST, clinic_id=clinic.id, product=product)
        if form.is_valid():
            dispense = form.save(commit=False)
            dispense.clinic = clinic
            dispense.product = product
            dispense.unit_price = product.selling_price or Decimal('0.00')
            dispense.dispensed_by = request.user
            active_appointment = _active_eye_appointment_for_patient(dispense.patient, clinic)
            if active_appointment:
                dispense.appointment = active_appointment
                dispense.encounter = get_or_create_encounter_for_appointment(active_appointment, request.user)
            dispense.save()

            result = dispense.deduct_stock()
            if result is False:
                dispense.delete()
                messages.error(request, f"Insufficient stock to dispense {product.display_name}.")
                return redirect('DurielEyeApp:dispense_optical', pk=product.pk)

            _sync_optical_dispense_to_billing(dispense, active_appointment, request.user)

            log_action(request, 'CREATE', dispense,
                       details=(f"Dispensed optical {product.display_name} x{dispense.quantity} "
                                f"to {dispense.patient.full_name}"))
            notify_role_handoff(
                clinic,
                ['ADMIN', 'RECEPTIONIST'],
                f"Optical product dispensed for {dispense.patient.full_name}. Billing updated.",
                link=reverse('core:billing_list'),
            )
            messages.success(
                request,
                f"Dispensed {product.display_name} x{dispense.quantity}. "
                f"₦{dispense.total_price} added to {dispense.patient.full_name}'s bill.",
            )
            return redirect('DurielEyeApp:optical_product_list')
    else:
        form = OpticalDispenseForm(clinic_id=clinic.id, product=product)

    return render(request, 'eye/optical/dispense.html',
                  {'form': form, 'product': product, 'clinic': clinic})


@login_required
@clinic_selected_required
@role_required(*OPTICAL_MANAGE_ROLES)
def optical_dispense_history(request):
    """Recent optical dispenses for the current eye clinic."""
    clinic = request.clinic
    dispenses = (OpticalDispense.objects
                 .filter(clinic=clinic)
                 .select_related('patient', 'product', 'dispensed_by')
                 .order_by('-dispensed_at')[:100])
    return render(request, 'eye/optical/dispense_history.html',
                  {'dispenses': dispenses, 'clinic': clinic})
