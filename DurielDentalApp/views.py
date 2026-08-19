import json
from datetime import datetime, time, timedelta
from html import escape

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.timezone import make_aware
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from core.decorators import clinic_selected_required, role_required
from core.utils import ensure_appointment_consultation_charge, ensure_billing_line_item, get_or_create_encounter_for_appointment
from core.models import Billing, Patient
from core.reporting import build_clinic_report_context, export_appointment_report, export_patient_report, export_financial_report
from core.permissions import DENTAL_CLINICAL_ROLES
from core.utils import log_action, notify_roles, notify_user_db, notify_role_handoff
from DurielMedicApp.models import Vitals
from .forms import (
    DentalAppointmentForm,
    DentalExamForm,
    DentalFollowUpClinicalForm,
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


DENTAL_FRONT_DESK_ROLES = ['ADMIN', 'RECEPTIONIST', 'NURSE']


def _clinic_id(request):
    return request.session.get('clinic_id')


def _paginate(request, queryset, page_param, per_page=2):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get(page_param, 1)
    try:
        return paginator.page(page_number)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


@login_required
@clinic_selected_required
def dental_dashboard(request):
    return redirect('core:clinic_dashboard')


@login_required
@clinic_selected_required
def dental_dashboard_detail(request):
    clinic_id = _clinic_id(request)
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    appointments = DentalAppointment.objects.filter(clinic_id=clinic_id, date=today).select_related('patient', 'provider').order_by('start_time')
    if request.user.role not in [*DENTAL_FRONT_DESK_ROLES, 'DENTIST']:
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
        appointment_type = ContentType.objects.get_for_model(DentalAppointment)
        qs = DentalAppointment.objects.filter(clinic_id=clinic_id).select_related('patient', 'provider').annotate(
            has_vitals=Exists(
                Vitals.objects.filter(
                    appointment_content_type=appointment_type,
                    appointment_object_id=OuterRef('pk'),
                )
            )
        )
        if self.request.GET.get('date'):
            qs = qs.filter(date=self.request.GET['date'])
        if self.request.GET.get('status'):
            qs = qs.filter(status=self.request.GET['status'])
        if self.request.user.role not in [*DENTAL_FRONT_DESK_ROLES, 'DENTIST']:
            qs = qs.filter(provider=self.request.user)
        return qs.order_by('-date', '-start_time')


class DentalAppointmentCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = DentalAppointment
    form_class = DentalAppointmentForm
    template_name = 'dental/appointments/appointment_form.html'
    success_url = reverse_lazy('DurielDentalApp:appointment_list')

    def test_func(self):
        return self.request.user.role in ['ADMIN', 'RECEPTIONIST', 'NURSE']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['clinic_id'] = _clinic_id(self.request)
        return kwargs

    def form_valid(self, form):
        form.instance.clinic_id = _clinic_id(self.request)
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request, 'CREATE', self.object, details=f"Created dental appointment for {self.object.patient.full_name}")
        notify_role_handoff(
            self.object.clinic,
            ['DENTIST'],
            f"New dental appointment for {self.object.patient.full_name} on {self.object.date}",
            link=reverse_lazy('DurielDentalApp:appointment_detail', kwargs={'pk': self.object.pk}),
            app_name='dental',
            object_id=self.object.pk,
            actor=self.request.user,
            provider=self.object.provider,
        )
        messages.success(self.request, 'Dental appointment scheduled.')
        return response


class DentalAppointmentUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = DentalAppointment
    form_class = DentalAppointmentForm
    template_name = 'dental/appointments/appointment_form.html'

    def test_func(self):
        return self.request.user.role in ['ADMIN', 'DENTIST', 'RECEPTIONIST', 'NURSE']

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


@login_required
@clinic_selected_required
@role_required('DENTIST')
def begin_consultation(request, pk):
    appointment = get_object_or_404(
        DentalAppointment.objects.select_related('patient', 'clinic', 'provider'),
        pk=pk,
        clinic_id=_clinic_id(request),
    )
    patient = appointment.patient
    if appointment.status == 'COMPLETED':
        messages.info(request, 'This dental consultation has already been completed.')
        return redirect('core:patient_detail', pk=patient.patient_id)

    with transaction.atomic():
        if appointment.status in ['SCHEDULED', 'CHECKED_IN']:
            appointment.status = 'IN_CHAIR'
            appointment.save(update_fields=['status', 'updated_at'])
        if patient.status != 'IN_CONSULTATION':
            patient.status = 'IN_CONSULTATION'
            patient.save(update_fields=['status'])
        get_or_create_encounter_for_appointment(appointment, request.user)

    log_action(request, 'UPDATE', appointment, details=f"Began dental consultation for {patient.full_name}")
    return redirect('core:patient_detail', pk=patient.patient_id)


@require_POST
@login_required
@clinic_selected_required
@role_required('DENTIST')
def complete_consultation(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic_id=_clinic_id(request))
    appointment = DentalAppointment.objects.filter(
        patient=patient,
        clinic_id=_clinic_id(request),
        status__in=['SCHEDULED', 'CHECKED_IN', 'IN_CHAIR'],
    ).order_by('-date', '-start_time').first()
    if not appointment:
        messages.error(request, 'No active dental appointment found for this patient.')
        return redirect('core:patient_detail', pk=patient.patient_id)

    with transaction.atomic():
        appointment.status = 'COMPLETED'
        appointment.save(update_fields=['status', 'updated_at'])
        patient.status = 'CONSULTATION_COMPLETE'
        patient.save(update_fields=['status'])
        ensure_appointment_consultation_charge(appointment, request.user, description='Dental consultation')

    log_action(request, 'UPDATE', appointment, details=f"Completed dental consultation for {patient.full_name}")
    notify_role_handoff(
        appointment.clinic,
        ['ADMIN', 'RECEPTIONIST', 'NURSE', 'DENTIST'],
        f"Dental consultation completed for {patient.full_name}. Billing/review pending.",
        link=f"{reverse_lazy('core:create_bill')}?patient={patient.patient_id}&appointment_id={appointment.pk}&appointment_type=dental",
        app_name='dental',
        object_id=appointment.pk,
        actor=request.user,
        provider=appointment.provider,
    )
    messages.success(request, 'Dental consultation completed.')
    return redirect('core:patient_detail', pk=patient.patient_id)


@require_POST
@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST', 'NURSE', 'DENTIST')
def update_appointment_status(request, pk, status):
    appointment = get_object_or_404(DentalAppointment, pk=pk, clinic_id=_clinic_id(request))
    valid = dict(DentalAppointment.STATUS_CHOICES)
    if status not in valid:
        messages.error(request, 'Invalid appointment status.')
    else:
        appointment.status = status
        appointment.save(update_fields=['status', 'updated_at'])
        log_action(request, 'UPDATE', appointment, details=f"Marked dental appointment {valid[status]}")
        if status == 'COMPLETED':
            ensure_appointment_consultation_charge(appointment, request.user, description='Dental consultation')
            notify_role_handoff(
                appointment.clinic,
                ['ADMIN', 'RECEPTIONIST', 'NURSE', 'DENTIST'],
                f"Dental appointment completed for {appointment.patient.full_name}. Billing/review pending.",
                link=f"{reverse_lazy('core:create_bill')}?patient={appointment.patient.patient_id}&appointment_id={appointment.pk}&appointment_type=dental",
                app_name='dental',
                object_id=appointment.pk,
                actor=request.user,
                provider=appointment.provider,
            )
        messages.success(request, f'Appointment marked {valid[status]}.')
    return redirect('DurielDentalApp:appointment_detail', pk=appointment.pk)


@login_required
@role_required('DENTIST')
def today_appointment_count(request):
    clinic_id = _clinic_id(request)
    count = 0
    if clinic_id:
        count = DentalAppointment.objects.filter(
            clinic_id=clinic_id,
            date=timezone.localdate(),
            status__in=['SCHEDULED', 'CHECKED_IN'],
        ).count()
    return JsonResponse({'count': count})


@login_required
@clinic_selected_required
@role_required('DENTIST')
def patient_dental_chart(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic_id=_clinic_id(request))
    return render(request, 'dental/patient_chart.html', {
        'patient': patient,
        'appointments': DentalAppointment.objects.filter(patient=patient).select_related('provider')[:10],
        'exams': _paginate(request, DentalExam.objects.filter(patient=patient), 'exams_page'),
        'plans': _paginate(request, DentalTreatmentPlan.objects.filter(patient=patient), 'plans_page'),
        'procedures': _paginate(request, DentalProcedure.objects.filter(patient=patient).select_related('performed_by'), 'procedures_page'),
        'followups': _paginate(request, DentalFollowUp.objects.filter(patient=patient), 'followups_page'),
        'records': _paginate(request, DentalMedicalRecord.objects.filter(patient=patient), 'records_page'),
    })


@login_required
@clinic_selected_required
@role_required('DENTIST')
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
            exam.encounter = get_or_create_encounter_for_appointment(appointment, request.user) if appointment else None
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
@role_required('DENTIST')
def create_treatment_plan(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic_id=_clinic_id(request))
    if request.method == 'POST':
        form = DentalTreatmentPlanForm(request.POST, patient=patient)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.patient = patient
            plan.clinic = patient.clinic
            if plan.exam and plan.exam.encounter_id:
                plan.encounter = plan.exam.encounter
            plan.created_by = request.user
            plan.save()
            log_action(request, 'CREATE', plan, details=f"Created dental treatment plan for {patient.full_name}")
            notify_roles(
                patient.clinic,
                ['ADMIN', 'RECEPTIONIST'],
                f"Dental treatment plan created for {patient.full_name}. Review billing/services.",
                link=reverse_lazy('DurielDentalApp:patient_chart', kwargs={'patient_id': patient.patient_id}),
                app_name='dental',
                object_id=plan.pk,
                exclude_user=request.user,
            )
            messages.success(request, 'Treatment plan saved.')
            return redirect('DurielDentalApp:patient_chart', patient_id=patient.patient_id)
    else:
        form = DentalTreatmentPlanForm(patient=patient)
    return render(request, 'dental/forms/form_page.html', {'form': form, 'title': 'Create Dental Treatment Plan', 'patient': patient})


@login_required
@clinic_selected_required
@role_required('DENTIST')
def record_procedure(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic_id=_clinic_id(request))
    if request.method == 'POST':
        form = DentalProcedureForm(request.POST, patient=patient)
        if form.is_valid():
            procedure = form.save(commit=False)
            procedure.patient = patient
            procedure.clinic = patient.clinic
            procedure.performed_by = request.user
            if procedure.appointment:
                procedure.encounter = get_or_create_encounter_for_appointment(procedure.appointment, request.user)
            elif procedure.treatment_plan and procedure.treatment_plan.encounter_id:
                procedure.encounter = procedure.treatment_plan.encounter
            procedure.save()
            if procedure.appointment and procedure.status == 'DONE':
                procedure.appointment.status = 'COMPLETED'
                procedure.appointment.save(update_fields=['status', 'updated_at'])
                ensure_appointment_consultation_charge(procedure.appointment, request.user, description='Dental consultation')
            if procedure.status == 'DONE':
                ensure_billing_line_item(
                    clinic=patient.clinic,
                    patient=patient,
                    appointment=procedure.appointment,
                    encounter=procedure.encounter,
                    source_obj=procedure,
                    source_type='PROCEDURE',
                    service=None,
                    description=f"Dental procedure: {procedure.procedure_name}",
                    unit_price=0,
                    created_by=request.user,
                    auto_approve=True,
                )
            log_action(request, 'CREATE', procedure, details=f"Recorded dental procedure for {patient.full_name}")
            notify_roles(
                patient.clinic,
                ['ADMIN', 'RECEPTIONIST'],
                f"Dental procedure recorded for {patient.full_name}. Review billing.",
                link=reverse_lazy('DurielDentalApp:patient_chart', kwargs={'patient_id': patient.patient_id}),
                app_name='dental',
                object_id=procedure.pk,
                exclude_user=request.user,
            )
            messages.success(request, 'Procedure recorded for billing and clinical history.')
            return redirect('DurielDentalApp:patient_chart', patient_id=patient.patient_id)
    else:
        form = DentalProcedureForm(patient=patient)
    return render(request, 'dental/forms/form_page.html', {'form': form, 'title': 'Record Dental Procedure', 'patient': patient})


@login_required
@clinic_selected_required
@role_required('DENTIST')
def schedule_follow_up(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id, clinic_id=_clinic_id(request))
    if request.method == 'POST':
        form = DentalFollowUpClinicalForm(request.POST, patient=patient)
        if form.is_valid():
            followup = form.save(commit=False)
            followup.patient = patient
            followup.clinic = patient.clinic
            followup.created_by = request.user
            followup.save()
            messages.success(request, 'Dental follow-up scheduled.')
            return redirect('DurielDentalApp:patient_chart', patient_id=patient.patient_id)
    else:
        form = DentalFollowUpClinicalForm(patient=patient)
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
@role_required('DENTIST')
def complete_follow_up(request, pk):
    followup = get_object_or_404(DentalFollowUp, pk=pk, clinic_id=_clinic_id(request))
    followup.completed = True
    followup.completed_at = timezone.now()
    followup.save(update_fields=['completed', 'completed_at'])
    messages.success(request, 'Follow-up completed.')
    return redirect('DurielDentalApp:followup_list')


@login_required
@clinic_selected_required
@role_required('DENTIST')
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
@role_required('DENTIST')
def procedure_list(request):
    procedures = DentalProcedure.objects.filter(clinic_id=_clinic_id(request)).select_related('patient', 'performed_by')
    if request.GET.get('q'):
        q = request.GET['q']
        procedures = procedures.filter(Q(patient__first_name__icontains=q) | Q(patient__last_name__icontains=q) | Q(procedure_name__icontains=q) | Q(tooth_numbers__icontains=q))
    return render(request, 'dental/procedures/list.html', {'procedures': procedures[:100]})


def _dental_file_config(file_type):
    configs = {
        'exam': {
            'model': DentalExam,
            'form': DentalExamForm,
            'title': 'Dental Exam',
            'date_attr': 'created_at',
            'sections': [
                ('Chief Complaint', 'chief_complaint'),
                ('Medical Alerts', 'medical_alerts'),
                ('Extraoral Exam', 'extraoral_exam'),
                ('Intraoral Exam', 'intraoral_exam'),
                ('Periodontal Findings', 'periodontal_findings'),
                ('Occlusion', 'get_occlusion_display'),
                ('Diagnosis', 'diagnosis'),
                ('Treatment Recommendation', 'treatment_recommendation'),
            ],
        },
        'plan': {
            'model': DentalTreatmentPlan,
            'form': DentalTreatmentPlanForm,
            'title': 'Dental Treatment Plan',
            'date_attr': 'created_at',
            'sections': [
                ('Title', 'title'),
                ('Diagnosis', 'diagnosis'),
                ('Proposed Treatment', 'proposed_treatment'),
                ('Priority', 'get_priority_display'),
                ('Status', 'get_status_display'),
                ('Consent Obtained', 'consent_obtained'),
                ('Consent Notes', 'consent_notes'),
            ],
        },
        'procedure': {
            'model': DentalProcedure,
            'form': DentalProcedureForm,
            'title': 'Dental Procedure',
            'date_attr': 'performed_at',
            'sections': [
                ('Procedure', 'procedure_name'),
                ('Tooth Numbers', 'tooth_numbers'),
                ('Materials Used', 'materials_used'),
                ('Anesthesia', 'anesthesia'),
                ('Status', 'get_status_display'),
                ('Notes', 'notes'),
                ('Performed By', 'performed_by'),
            ],
        },
        'followup': {
            'model': DentalFollowUp,
            'form': DentalFollowUpClinicalForm,
            'title': 'Dental Follow-up',
            'date_attr': 'scheduled_date',
            'sections': [
                ('Treatment Plan', 'treatment_plan'),
                ('Reason', 'reason'),
                ('Scheduled Date', 'scheduled_date'),
                ('Scheduled Time', 'scheduled_time'),
                ('Notes', 'notes'),
                ('Completed', 'completed'),
            ],
        },
        'record': {
            'model': DentalMedicalRecord,
            'form': DentalMedicalRecordForm,
            'title': 'Dental Record',
            'date_attr': 'created_at',
            'sections': [
                ('Record Type', 'get_record_type_display'),
                ('Title', 'title'),
                ('Description', 'description'),
            ],
        },
    }
    try:
        return configs[file_type]
    except KeyError:
        raise Http404('Dental file type not found.')


def _field_value(obj, attr):
    value = getattr(obj, attr, '')
    if callable(value):
        value = value()
    if value is True:
        return 'Yes'
    if value is False:
        return 'No'
    return value or ''


def _get_dental_file(request, file_type, pk):
    config = _dental_file_config(file_type)
    return config, get_object_or_404(config['model'], pk=pk, clinic_id=_clinic_id(request))


@login_required
@clinic_selected_required
@role_required('DENTIST')
def dental_file_detail(request, file_type, pk):
    config, obj = _get_dental_file(request, file_type, pk)
    sections = [(label, _field_value(obj, attr)) for label, attr in config['sections']]
    return render(request, 'dental/forms/detail_page.html', {
        'object': obj,
        'file_type': file_type,
        'title': config['title'],
        'patient': obj.patient,
        'sections': sections,
    })


@login_required
@clinic_selected_required
@role_required('DENTIST')
def dental_file_edit(request, file_type, pk):
    config, obj = _get_dental_file(request, file_type, pk)
    form_class = config['form']
    form_kwargs = {'instance': obj}
    if file_type in ['plan', 'procedure', 'followup']:
        form_kwargs['patient'] = obj.patient
    if request.method == 'POST':
        form = form_class(request.POST, **form_kwargs)
        if form.is_valid():
            updated = form.save(commit=False)
            if file_type == 'exam' and 'tooth_chart_json' in form.cleaned_data:
                updated.tooth_chart = form.cleaned_data['tooth_chart_json']
            updated.save()
            log_action(request, 'UPDATE', updated, details=f"Updated {config['title'].lower()} for {obj.patient.full_name}")
            messages.success(request, f'{config["title"]} updated.')
            return redirect('DurielDentalApp:dental_file_detail', file_type=file_type, pk=obj.pk)
    else:
        if file_type == 'exam':
            form_kwargs['initial'] = {'tooth_chart_json': json.dumps(obj.tooth_chart or {})}
        form = form_class(**form_kwargs)
    return render(request, 'dental/forms/form_page.html', {
        'form': form,
        'title': f'Edit {config["title"]}',
        'patient': obj.patient,
        'object': obj,
    })


@login_required
@clinic_selected_required
@role_required('DENTIST')
def dental_file_pdf(request, file_type, pk):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    config, obj = _get_dental_file(request, file_type, pk)
    patient = obj.patient
    log_action(request, 'UPDATE', obj, details=f"Exported {config['title'].lower()} PDF for {patient.full_name}")
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=0.75 * inch, leftMargin=0.75 * inch, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, spaceAfter=20, textColor=colors.darkblue)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=12, spaceBefore=12, spaceAfter=6, textColor=colors.darkblue)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, spaceAfter=8, leading=14)
    story = [
        Paragraph(config['title'], title_style),
        Paragraph(f"<b>Patient:</b> {escape(str(patient.full_name))}", body_style),
        Paragraph(f"<b>Patient ID:</b> {escape(str(patient.patient_id))}", body_style),
    ]
    date_value = _field_value(obj, config['date_attr'])
    if date_value:
        story.append(Paragraph(f"<b>Date:</b> {escape(str(date_value))}", body_style))
    story.append(Spacer(1, 0.25 * inch))
    for label, attr in config['sections']:
        value = _field_value(obj, attr)
        if value:
            story.append(Paragraph(label, heading_style))
            story.append(Paragraph(escape(str(value)).replace('\n', '<br/>'), body_style))
    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="dental_{file_type}_{patient.patient_id}_{obj.pk}.pdf"'
    return response


@login_required
@clinic_selected_required
@role_required('ADMIN')
def generate_dental_report(request):
    """Dental analytics dashboard — same shared report as General/Eye."""
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
        if report_type == 'appointments':
            return export_appointment_report(DentalAppointment, start_date, end_date, clinic_id)
        elif report_type == 'patients':
            return export_patient_report(start_date, end_date, clinic_id)
        elif report_type == 'financial':
            return export_financial_report(start_date, end_date, clinic_id)

    context = build_clinic_report_context(clinic_id, DentalAppointment, start_date, end_date)
    return render(request, 'reports/generate_report.html', context)
