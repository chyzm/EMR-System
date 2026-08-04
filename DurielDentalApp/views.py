from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from core.decorators import clinic_selected_required, role_required
from core.models import Billing, Patient
from core.utils import log_action
from .forms import (
    DentalAppointmentForm,
    DentalExamForm,
    DentalFollowUpForm,
    DentalMedicalRecordForm,
    DentalProcedureForm,
    DentalTreatmentPlanForm,
)
from .models import (
    DentalAppointment,
    DentalExam,
    DentalFollowUp,
    DentalMedicalRecord,
    DentalProcedure,
    DentalTreatmentPlan,
)


DENTAL_CLINICAL_ROLES = ['ADMIN', 'DOCTOR', 'NURSE']
DENTAL_FRONT_DESK_ROLES = ['ADMIN', 'RECEPTIONIST', 'NURSE']


def _clinic_id(request):
    return request.session.get('clinic_id')


@login_required
@clinic_selected_required
def dental_dashboard(request):
    clinic_id = _clinic_id(request)
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    appointments = DentalAppointment.objects.filter(clinic_id=clinic_id, date=today).select_related('patient', 'provider').order_by('start_time')
    if request.user.role not in DENTAL_FRONT_DESK_ROLES:
        appointments = appointments.filter(provider=request.user)

    stats = {
        'total_patients': Patient.objects.filter(clinic_id=clinic_id).count(),
        'today_appointments': appointments.count(),
        'week_appointments': DentalAppointment.objects.filter(clinic_id=clinic_id, date__range=[week_start, week_end]).count(),
        'open_treatment_plans': DentalTreatmentPlan.objects.filter(clinic_id=clinic_id, status__in=['PROPOSED', 'ACCEPTED', 'IN_PROGRESS']).count(),
        'procedures_today': DentalProcedure.objects.filter(clinic_id=clinic_id, performed_at__date=today).count(),
        'pending_followups': DentalFollowUp.objects.filter(clinic_id=clinic_id, completed=False, scheduled_date__gte=today).count(),
        'pending_bills': Billing.objects.filter(clinic_id=clinic_id, status__in=['PENDING', 'PARTIAL']).count(),
        'outstanding_balance': Billing.objects.filter(clinic_id=clinic_id, status__in=['PENDING', 'PARTIAL']).aggregate(total=Sum('amount'))['total'] or 0,
    }
    recent_patients = Patient.objects.filter(clinic_id=clinic_id).order_by('-created_at')[:8]
    recent_procedures = DentalProcedure.objects.filter(clinic_id=clinic_id).select_related('patient', 'performed_by')[:8]

    return render(request, 'dental/dashboard.html', {
        'stats': stats,
        'appointments': appointments,
        'recent_patients': recent_patients,
        'recent_procedures': recent_procedures,
        'today': today,
    })


class DentalAppointmentListView(LoginRequiredMixin, ListView):
    model = DentalAppointment
    template_name = 'dental/appointments/appointment_list.html'
    context_object_name = 'appointments'
    paginate_by = 20

    def get_queryset(self):
        clinic_id = _clinic_id(self.request)
        qs = DentalAppointment.objects.filter(clinic_id=clinic_id).select_related('patient', 'provider')
        if self.request.GET.get('date'):
            qs = qs.filter(date=self.request.GET['date'])
        if self.request.GET.get('status'):
            qs = qs.filter(status=self.request.GET['status'])
        if self.request.user.role not in DENTAL_FRONT_DESK_ROLES:
            qs = qs.filter(provider=self.request.user)
        return qs.order_by('date', 'start_time')


class DentalAppointmentCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = DentalAppointment
    form_class = DentalAppointmentForm
    template_name = 'dental/appointments/appointment_form.html'
    success_url = reverse_lazy('DurielDentalApp:appointment_list')

    def test_func(self):
        return self.request.user.role in ['ADMIN', 'DOCTOR', 'RECEPTIONIST', 'NURSE']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['clinic_id'] = _clinic_id(self.request)
        return kwargs

    def form_valid(self, form):
        form.instance.clinic_id = _clinic_id(self.request)
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request, 'CREATE', self.object, details=f"Created dental appointment for {self.object.patient.full_name}")
        messages.success(self.request, 'Dental appointment scheduled.')
        return response


class DentalAppointmentUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = DentalAppointment
    form_class = DentalAppointmentForm
    template_name = 'dental/appointments/appointment_form.html'

    def test_func(self):
        return self.request.user.role in ['ADMIN', 'DOCTOR', 'RECEPTIONIST', 'NURSE']

    def get_queryset(self):
        return DentalAppointment.objects.filter(clinic_id=_clinic_id(self.request))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['clinic_id'] = _clinic_id(self.request)
        return kwargs

    def get_success_url(self):
        return reverse_lazy('DurielDentalApp:appointment_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request, 'UPDATE', self.object, details=f"Updated dental appointment for {self.object.patient.full_name}")
        messages.success(self.request, 'Dental appointment updated.')
        return response


@login_required
@clinic_selected_required
def appointment_detail(request, pk):
    appointment = get_object_or_404(
        DentalAppointment.objects.select_related('patient', 'provider'),
        pk=pk,
        clinic_id=_clinic_id(request),
    )
    return render(request, 'dental/appointments/appointment_detail.html', {'appointment': appointment})


@require_POST
@login_required
@clinic_selected_required
def update_appointment_status(request, pk, status):
    appointment = get_object_or_404(DentalAppointment, pk=pk, clinic_id=_clinic_id(request))
    valid = dict(DentalAppointment.STATUS_CHOICES)
    if status not in valid:
        messages.error(request, 'Invalid appointment status.')
    else:
        appointment.status = status
        appointment.save(update_fields=['status', 'updated_at'])
        log_action(request, 'UPDATE', appointment, details=f"Marked dental appointment {valid[status]}")
        messages.success(request, f'Appointment marked {valid[status]}.')
    return redirect('DurielDentalApp:appointment_detail', pk=appointment.pk)


@login_required
@role_required('DOCTOR')
def today_appointment_count(request):
    clinic_id = _clinic_id(request)
    count = 0
    if clinic_id:
        count = DentalAppointment.objects.filter(
            clinic_id=clinic_id,
            provider=request.user,
            date=timezone.localdate(),
            status__in=['SCHEDULED', 'CHECKED_IN'],
        ).count()
    return JsonResponse({'count': count})


@login_required
@clinic_selected_required
def patient_dental_chart(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic_id=_clinic_id(request))
    return render(request, 'dental/patient_chart.html', {
        'patient': patient,
        'appointments': DentalAppointment.objects.filter(patient=patient).select_related('provider')[:10],
        'exams': DentalExam.objects.filter(patient=patient)[:10],
        'plans': DentalTreatmentPlan.objects.filter(patient=patient)[:10],
        'procedures': DentalProcedure.objects.filter(patient=patient).select_related('performed_by')[:10],
        'followups': DentalFollowUp.objects.filter(patient=patient)[:10],
        'records': DentalMedicalRecord.objects.filter(patient=patient)[:10],
    })


@login_required
@clinic_selected_required
@role_required('ADMIN', 'DOCTOR', 'NURSE')
def record_exam(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic_id=_clinic_id(request))
    appointment = DentalAppointment.objects.filter(patient=patient, status__in=['CHECKED_IN', 'IN_CHAIR', 'SCHEDULED']).order_by('-date', '-start_time').first()
    if request.method == 'POST':
        form = DentalExamForm(request.POST)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.patient = patient
            exam.clinic = patient.clinic
            exam.appointment = appointment
            exam.tooth_chart = form.cleaned_data['tooth_chart_json']
            exam.created_by = request.user
            exam.save()
            if appointment and appointment.status == 'SCHEDULED':
                appointment.status = 'IN_CHAIR'
                appointment.save(update_fields=['status', 'updated_at'])
            log_action(request, 'CREATE', exam, details=f"Recorded dental exam for {patient.full_name}")
            messages.success(request, 'Dental exam recorded.')
            return redirect('DurielDentalApp:patient_chart', patient_id=patient.patient_id)
    else:
        form = DentalExamForm()
    return render(request, 'dental/forms/form_page.html', {'form': form, 'title': 'Record Dental Exam', 'patient': patient})


@login_required
@clinic_selected_required
@role_required('ADMIN', 'DOCTOR')
def create_treatment_plan(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic_id=_clinic_id(request))
    if request.method == 'POST':
        form = DentalTreatmentPlanForm(request.POST, patient=patient)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.patient = patient
            plan.clinic = patient.clinic
            plan.created_by = request.user
            plan.save()
            log_action(request, 'CREATE', plan, details=f"Created dental treatment plan for {patient.full_name}")
            messages.success(request, 'Treatment plan saved.')
            return redirect('DurielDentalApp:patient_chart', patient_id=patient.patient_id)
    else:
        form = DentalTreatmentPlanForm(patient=patient)
    return render(request, 'dental/forms/form_page.html', {'form': form, 'title': 'Create Dental Treatment Plan', 'patient': patient})


@login_required
@clinic_selected_required
@role_required('ADMIN', 'DOCTOR', 'NURSE')
def record_procedure(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic_id=_clinic_id(request))
    if request.method == 'POST':
        form = DentalProcedureForm(request.POST, patient=patient)
        if form.is_valid():
            procedure = form.save(commit=False)
            procedure.patient = patient
            procedure.clinic = patient.clinic
            procedure.performed_by = request.user
            procedure.save()
            if procedure.appointment and procedure.status == 'DONE':
                procedure.appointment.status = 'COMPLETED'
                procedure.appointment.save(update_fields=['status', 'updated_at'])
            log_action(request, 'CREATE', procedure, details=f"Recorded dental procedure for {patient.full_name}")
            messages.success(request, 'Procedure recorded for billing and clinical history.')
            return redirect('DurielDentalApp:patient_chart', patient_id=patient.patient_id)
    else:
        form = DentalProcedureForm(patient=patient)
    return render(request, 'dental/forms/form_page.html', {'form': form, 'title': 'Record Dental Procedure', 'patient': patient})


@login_required
@clinic_selected_required
def schedule_follow_up(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic_id=_clinic_id(request))
    if request.method == 'POST':
        form = DentalFollowUpForm(request.POST, patient=patient)
        if form.is_valid():
            followup = form.save(commit=False)
            followup.patient = patient
            followup.clinic = patient.clinic
            followup.created_by = request.user
            followup.save()
            messages.success(request, 'Dental follow-up scheduled.')
            return redirect('DurielDentalApp:patient_chart', patient_id=patient.patient_id)
    else:
        form = DentalFollowUpForm(patient=patient)
    return render(request, 'dental/forms/form_page.html', {'form': form, 'title': 'Schedule Dental Follow-up', 'patient': patient})


class DentalFollowUpListView(LoginRequiredMixin, ListView):
    model = DentalFollowUp
    template_name = 'dental/followups/list.html'
    context_object_name = 'followups'
    paginate_by = 20

    def get_queryset(self):
        return DentalFollowUp.objects.filter(clinic_id=_clinic_id(self.request)).select_related('patient').order_by('scheduled_date', 'scheduled_time')


@require_POST
@login_required
@clinic_selected_required
def complete_follow_up(request, pk):
    followup = get_object_or_404(DentalFollowUp, pk=pk, clinic_id=_clinic_id(request))
    followup.completed = True
    followup.completed_at = timezone.now()
    followup.save(update_fields=['completed', 'completed_at'])
    messages.success(request, 'Follow-up completed.')
    return redirect('DurielDentalApp:followup_list')


@login_required
@clinic_selected_required
def add_medical_record(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic_id=_clinic_id(request))
    if request.method == 'POST':
        form = DentalMedicalRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.patient = patient
            record.clinic = patient.clinic
            record.created_by = request.user
            record.save()
            log_action(request, 'CREATE', record, details=f"Added dental record for {patient.full_name}")
            messages.success(request, 'Dental record added.')
            return redirect('DurielDentalApp:patient_chart', patient_id=patient.patient_id)
    else:
        form = DentalMedicalRecordForm()
    return render(request, 'dental/forms/form_page.html', {'form': form, 'title': 'Add Dental Record', 'patient': patient})


@login_required
@clinic_selected_required
def procedure_list(request):
    procedures = DentalProcedure.objects.filter(clinic_id=_clinic_id(request)).select_related('patient', 'performed_by')
    if request.GET.get('q'):
        q = request.GET['q']
        procedures = procedures.filter(Q(patient__first_name__icontains=q) | Q(patient__last_name__icontains=q) | Q(procedure_name__icontains=q) | Q(tooth_numbers__icontains=q))
    return render(request, 'dental/procedures/list.html', {'procedures': procedures[:100]})
