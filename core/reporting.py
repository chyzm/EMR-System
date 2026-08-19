"""Shared reporting helpers used by every clinic type.

The General clinic historically owned a rich analytics dashboard and CSV
exporters. This module extracts that logic so the Eye and Dental clinics can
render the exact same ``reports/generate_report.html`` dashboard and export the
same CSVs. The only per-clinic input is the appointment model
(``Appointment`` / ``EyeAppointment`` / ``DentalAppointment``); every other
figure comes from shared ``core`` models (Billing, BillingLineItem, Patient,
Prescription, LabTestOrder) so the numbers stay consistent across clinics.

Nothing here writes to the database — these are read-only aggregations.
"""

import csv
from datetime import timedelta

from django.db import models
from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.urls import reverse

from core.models import (
    Billing,
    BillingLineItem,
    ClinicMedication,
    LabTestOrder,
    Patient,
    Prescription,
)


def _effective_amount_expr():
    """Bill amount after any discount, matching billing_list / General report."""
    return models.Case(
        models.When(discount_type__in=['PERCENTAGE', 'FIXED'], then=F('final_amount')),
        models.When(final_amount__gt=0, then=F('final_amount')),
        default=F('amount'),
        output_field=DecimalField(max_digits=10, decimal_places=2),
    )


def build_clinic_report_context(clinic_id, appointment_model, start_date, end_date,
                                *, extra_attention_items=None):
    """Return the analytics-dashboard context shared by all clinic reports.

    Args:
        clinic_id: active clinic id.
        appointment_model: the per-clinic appointment model class.
        start_date, end_date: timezone-aware datetimes bounding the period.
        extra_attention_items: optional list of ``{'label', 'count', 'url'}``
            dicts for clinic-specific queues (e.g. General physio/nurse/follow-up).
            They are merged with the universal attention items and re-sorted.
    """
    effective_amount_expr = _effective_amount_expr()

    # ---- Appointments ----
    appointment_stats = appointment_model.objects.filter(
        clinic_id=clinic_id,
        date__range=[start_date.date(), end_date.date()],
    ).values('status').annotate(count=Count('id'))
    appointment_counts = {row['status']: row['count'] for row in appointment_stats}
    total_appointments = sum(appointment_counts.values())
    completed_appointments = appointment_counts.get('COMPLETED', 0)
    other_appointments = max(total_appointments - completed_appointments, 0)
    appointment_completion_rate = round((completed_appointments / total_appointments) * 100, 1) if total_appointments else 0

    # ---- Patients ----
    patient_stats = Patient.objects.filter(
        clinic_id=clinic_id,
        created_at__range=[start_date, end_date],
    ).aggregate(total=Count('patient_id'))
    total_patients = Patient.objects.filter(clinic_id=clinic_id).count()
    new_patient_ids = set(Patient.objects.filter(
        clinic_id=clinic_id,
        created_at__range=[start_date, end_date],
    ).values_list('patient_id', flat=True))
    seen_patient_ids = set(appointment_model.objects.filter(
        clinic_id=clinic_id,
        date__range=[start_date.date(), end_date.date()],
    ).values_list('patient_id', flat=True))
    returning_patients = max(len(seen_patient_ids - new_patient_ids), 0)

    # ---- Financials (current + previous period) ----
    bills_for_totals = Billing.objects.filter(
        clinic_id=clinic_id,
        service_date__range=[start_date.date(), end_date.date()],
    ).annotate(effective_amount=effective_amount_expr)
    financial_stats = bills_for_totals.aggregate(
        total_amount=Coalesce(Sum('effective_amount', output_field=DecimalField()), Value(0, output_field=DecimalField())),
        total_paid=Coalesce(Sum('paid_amount', output_field=DecimalField()), Value(0, output_field=DecimalField())),
    )
    total_amount = financial_stats['total_amount'] or 0
    total_paid = financial_stats['total_paid'] or 0
    outstanding = total_amount - total_paid
    collection_rate = round((total_paid / total_amount) * 100, 1) if total_amount else 0
    avg_revenue_per_patient = (total_amount / len(seen_patient_ids)) if seen_patient_ids else 0
    period_days = max((end_date.date() - start_date.date()).days + 1, 1)
    previous_end = start_date - timedelta(seconds=1)
    previous_start = previous_end - timedelta(days=period_days - 1)
    previous_bills = Billing.objects.filter(
        clinic_id=clinic_id,
        service_date__range=[previous_start.date(), previous_end.date()],
    ).annotate(effective_amount=effective_amount_expr)
    previous_financial = previous_bills.aggregate(
        total_amount=Coalesce(Sum('effective_amount', output_field=DecimalField()), Value(0, output_field=DecimalField())),
        total_paid=Coalesce(Sum('paid_amount', output_field=DecimalField()), Value(0, output_field=DecimalField())),
    )
    previous_total_amount = previous_financial['total_amount'] or 0
    revenue_delta = total_amount - previous_total_amount
    revenue_delta_percent = round((revenue_delta / previous_total_amount) * 100, 1) if previous_total_amount else None
    previous_new_patients = Patient.objects.filter(
        clinic_id=clinic_id,
        created_at__range=[previous_start, previous_end],
    ).count()
    new_patient_delta = (patient_stats['total'] or 0) - previous_new_patients
    revenue_per_patient_target = 40000
    revenue_per_patient_above_target = avg_revenue_per_patient >= revenue_per_patient_target
    patient_mix_total = (patient_stats['total'] or 0) + returning_patients
    new_patient_percent = round(((patient_stats['total'] or 0) / patient_mix_total) * 100, 1) if patient_mix_total else 0
    returning_patient_percent = round((returning_patients / patient_mix_total) * 100, 1) if patient_mix_total else 0
    outstanding_percent = round((outstanding / total_amount) * 100, 1) if total_amount else 0

    # ---- Service performance ----
    billing_line_items = BillingLineItem.objects.filter(
        clinic_id=clinic_id,
        created_at__range=[start_date, end_date],
    )
    top_services = billing_line_items.exclude(status='VOIDED').values(
        'description', 'source_type',
    ).annotate(
        total=Coalesce(Sum('total_amount', output_field=DecimalField()), Value(0, output_field=DecimalField())),
        count=Count('id'),
    ).order_by('-total', '-count')[:8]

    # ---- Operational queues (universal, all shared core models) ----
    due_billing_count = BillingLineItem.objects.filter(
        clinic_id=clinic_id,
        status__in=['DRAFT', 'APPROVED'],
        bill__isnull=True,
    ).count()
    pending_lab_count = LabTestOrder.objects.filter(
        clinic_id=clinic_id,
        status__in=['ORDERED', 'IN_QUEUE', 'SAMPLE_COLLECTED', 'PROCESSING'],
    ).count()
    low_stock_count = ClinicMedication.objects.filter(
        clinic_id=clinic_id,
        quantity_in_stock__lte=F('minimum_stock_level'),
        status='ACTIVE',
    ).count()

    # ---- Provider activity / revenue ----
    provider_activity = appointment_model.objects.filter(
        clinic_id=clinic_id,
        date__range=[start_date.date(), end_date.date()],
    ).values(
        'provider__first_name', 'provider__last_name', 'provider__username', 'provider__role',
    ).annotate(
        total=Count('id'),
        completed=Count('id', filter=Q(status='COMPLETED')),
    ).order_by('-completed', '-total')[:8]
    provider_revenue = BillingLineItem.objects.filter(
        clinic_id=clinic_id,
        created_at__range=[start_date, end_date],
    ).exclude(
        status='VOIDED',
    ).values(
        'created_by__first_name', 'created_by__last_name', 'created_by__username', 'created_by__role',
    ).annotate(
        revenue=Coalesce(Sum('total_amount', output_field=DecimalField()), Value(0, output_field=DecimalField())),
        count=Count('id'),
    ).order_by('-revenue', '-count')[:8]

    # ---- Clinical volume ----
    lab_stats = LabTestOrder.objects.filter(
        clinic_id=clinic_id,
        ordered_at__range=[start_date, end_date],
    ).values('status').annotate(count=Count('id')).order_by('status')
    prescription_count = Prescription.objects.filter(
        patient__clinic_id=clinic_id,
        date_prescribed__range=[start_date, end_date],
    ).count()
    try:
        from DurielMedicApp.models import Admission
        admission_stats = Admission.objects.filter(
            clinic_id=clinic_id,
            date_admitted__range=[start_date, end_date],
        ).aggregate(
            total=Count('id'),
            discharged=Count('id', filter=Q(discharged=True)),
        )
    except Exception:
        admission_stats = {'total': 0, 'discharged': 0}

    recent_unpaid_bills = bills_for_totals.filter(
        status__in=['PENDING', 'PARTIAL'],
    ).select_related('patient').order_by('-service_date', '-id')[:8]

    # ---- Needs attention (universal + clinic-specific) ----
    attention_items = [
        {'label': 'Patients due for billing', 'count': due_billing_count, 'url': reverse('core:billing_list')},
        {'label': 'Pending lab orders', 'count': pending_lab_count, 'url': reverse('core:lab_queue')},
        {'label': 'Low stock medicines', 'count': low_stock_count, 'url': reverse('core:low_stock_report')},
    ]
    if extra_attention_items:
        attention_items.extend(extra_attention_items)
    attention_items = sorted(attention_items, key=lambda item: (item['count'] == 0, -item['count'], item['label']))

    # ---- Insight cards ----
    insight_cards = []
    if outstanding == 0 and total_amount > 0:
        insight_cards.append({
            'tone': 'amber',
            'title': 'Billing Capture Check',
            'message': 'Outstanding is ₦0, but verify all completed work has reached billing before closing this period.',
        })
    elif outstanding > 0:
        insight_cards.append({
            'tone': 'red',
            'title': 'Collection Follow-up',
            'message': f'₦{outstanding:,.0f} remains outstanding. Review unpaid bills and follow up on partial payments.',
        })
    if patient_mix_total and returning_patients == 0:
        insight_cards.append({
            'tone': 'blue',
            'title': 'Retention Watch',
            'message': f'All {patient_mix_total} patients seen in this period were new. Track follow-ups as patient volume grows.',
        })
    if avg_revenue_per_patient and not revenue_per_patient_above_target:
        insight_cards.append({
            'tone': 'amber',
            'title': 'Revenue Per Patient Below Target',
            'message': f'Average revenue per patient is below the ₦{revenue_per_patient_target:,.0f} benchmark.',
        })
    if not insight_cards:
        insight_cards.append({
            'tone': 'green',
            'title': 'Stable Period',
            'message': 'No urgent business exceptions were detected for this report period.',
        })

    return {
        'start_date': start_date.date(),
        'end_date': end_date.date(),
        'appointment_stats': appointment_stats,
        'appointment_counts': appointment_counts,
        'total_appointments': total_appointments,
        'completed_appointments': completed_appointments,
        'other_appointments': other_appointments,
        'appointment_completion_rate': appointment_completion_rate,
        'patient_stats': patient_stats,
        'total_patients': total_patients,
        'returning_patients': returning_patients,
        'financial_stats': financial_stats,
        'outstanding': outstanding,
        'outstanding_percent': outstanding_percent,
        'collection_rate': collection_rate,
        'avg_revenue_per_patient': avg_revenue_per_patient,
        'revenue_per_patient_target': revenue_per_patient_target,
        'revenue_per_patient_above_target': revenue_per_patient_above_target,
        'previous_total_amount': previous_total_amount,
        'revenue_delta': revenue_delta,
        'revenue_delta_percent': revenue_delta_percent,
        'new_patient_delta': new_patient_delta,
        'new_patient_percent': new_patient_percent,
        'returning_patient_percent': returning_patient_percent,
        'top_services': top_services,
        'provider_activity': provider_activity,
        'provider_revenue': provider_revenue,
        'lab_stats': lab_stats,
        'prescription_count': prescription_count,
        'admission_stats': admission_stats,
        'recent_unpaid_bills': recent_unpaid_bills,
        'attention_items': attention_items,
        'insight_cards': insight_cards,
    }


def export_appointment_report(appointment_model, start_date, end_date, clinic_id):
    """CSV of appointments in range for any clinic's appointment model."""
    appointments = appointment_model.objects.filter(
        clinic_id=clinic_id,
        date__range=[start_date.date(), end_date.date()],
    ).select_related('patient', 'provider').order_by('date', 'start_time')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="appointments_report_{start_date.date()}_to_{end_date.date()}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Date', 'Time', 'Patient', 'Provider', 'Status', 'Reason'])
    for appt in appointments:
        reason = getattr(appt, 'reason', '') or getattr(appt, 'chief_complaint', '') or ''
        writer.writerow([
            appt.date,
            f"{appt.start_time} - {appt.end_time}",
            appt.patient.full_name if appt.patient else '',
            appt.provider.get_full_name() if appt.provider else '',
            appt.get_status_display(),
            reason,
        ])
    return response


def export_patient_report(start_date, end_date, clinic_id):
    """CSV of patients registered in range for a clinic."""
    patients = Patient.objects.filter(
        clinic_id=clinic_id,
        created_at__range=[start_date, end_date],
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
            patient.created_at.strftime('%Y-%m-%d %H:%M'),
        ])
    return response


def export_financial_report(start_date, end_date, clinic_id):
    """CSV of bills + totals in range for a clinic."""
    try:
        bills = Billing.objects.filter(
            clinic_id=clinic_id,
            service_date__range=[start_date.date(), end_date.date()],
        ).select_related('patient').order_by('service_date')

        totals = bills.aggregate(
            total_billed=Coalesce(Sum(_effective_amount_expr()), Value(0, output_field=DecimalField())),
            total_paid=Coalesce(Sum('paid_amount', output_field=DecimalField()), Value(0, output_field=DecimalField())),
        )
        totals['outstanding'] = (totals['total_billed'] or 0) - (totals['total_paid'] or 0)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="financial_report_'
            f'{start_date.date()}_to_{end_date.date()}.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(['Bill Date', 'Patient', 'Amount', 'Paid', 'Balance', 'Status', 'Description'])
        for bill in bills:
            amount = bill.get_effective_amount() or 0
            paid = bill.paid_amount or 0
            balance = amount - paid
            writer.writerow([
                bill.service_date.strftime('%Y-%m-%d') if bill.service_date else '',
                bill.patient.full_name if bill.patient else 'Unknown Patient',
                amount,
                paid,
                balance,
                bill.get_status_display() if bill.status else '',
                bill.description or '',
            ])
        writer.writerow([])
        writer.writerow(['TOTALS', '',
                         totals['total_billed'] or 0,
                         totals['total_paid'] or 0,
                         totals['outstanding'],
                         '', ''])
        return response
    except Exception as exc:  # pragma: no cover - mirrors General report's guard
        print(f"Error generating financial report: {str(exc)}")
        return HttpResponse(
            "An error occurred while generating the report. Please try again later.",
            content_type='text/plain',
            status=500,
        )
