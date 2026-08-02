import json
from decimal import Decimal
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.contrib.contenttypes.models import ContentType
from core.models import Patient, Clinic, Billing, Payment
from core.forms import PatientForm, BillingForm
from DurielMedicApp.forms import VitalsForm, MedicalRecordForm, AdmissionForm, FollowUpForm
from DurielMedicApp.models import Appointment, Vitals, MedicalRecord, Admission, FollowUp
from DurielEyeApp.models import EyeAppointment
from django.contrib import messages
from django.utils import timezone


@login_required
@require_POST
@csrf_exempt
def sync_queue(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON payload'}, status=400)

    queue_items = payload.get('items', [])
    if not isinstance(queue_items, list):
        return JsonResponse({'success': False, 'error': 'items must be a list'}, status=400)

    processed = []
    failed = []

    for item in queue_items:
        action_type = item.get('action')
        form_key = item.get('formKey', '')
        data = item.get('payload', {})

        if action_type == 'patient_create':
            try:
                clinic_id = request.session.get('clinic_id')
                if not clinic_id:
                    raise ValueError('No clinic selected')

                clinic = Clinic.objects.get(id=clinic_id)
                patient_data = dict(data)
                patient_data['clinic'] = clinic.id
                patient_data['created_by'] = request.user.id

                form = PatientForm(patient_data, request=request)
                if form.is_valid():
                    patient = form.save(commit=True)
                    processed.append({'formKey': form_key, 'patient_id': patient.patient_id})
                else:
                    failed.append({'formKey': form_key, 'error': form.errors})
            except Exception as exc:
                failed.append({'formKey': form_key, 'error': str(exc)})
        elif action_type == 'record_vitals':
            try:
                appointment_id = data.get('appointment')
                appointment = Appointment.objects.get(id=appointment_id)
                form = VitalsForm(data, instance=None)
                if form.is_valid():
                    vitals = form.save(commit=False)
                    vitals.appointment = appointment
                    vitals.save()
                    processed.append({'formKey': form_key, 'vitals_id': vitals.id})
                else:
                    failed.append({'formKey': form_key, 'error': form.errors})
            except Exception as exc:
                failed.append({'formKey': form_key, 'error': str(exc)})
        elif action_type == 'add_medical_record':
            try:
                patient_id = data.get('patient_id') or data.get('patient')
                if not patient_id:
                    raise ValueError('No patient selected')
                patient = Patient.objects.get(patient_id=patient_id)
                form = MedicalRecordForm(data)
                if form.is_valid():
                    record = form.save(commit=False)
                    record.patient = patient
                    record.created_by = request.user
                    record.save()
                    processed.append({'formKey': form_key, 'record_id': record.id})
                else:
                    failed.append({'formKey': form_key, 'error': form.errors})
            except Exception as exc:
                failed.append({'formKey': form_key, 'error': str(exc)})
        elif action_type == 'admit_patient':
            try:
                patient_id = data.get('patient_id') or data.get('patient')
                if not patient_id:
                    raise ValueError('No patient selected')
                patient = Patient.objects.get(patient_id=patient_id)
                clinic_id = request.session.get('clinic_id') or patient.clinic_id
                form = AdmissionForm(data)
                if form.is_valid():
                    admission = form.save(commit=False)
                    admission.patient = patient
                    admission.clinic_id = clinic_id
                    admission.admitted_by = request.user
                    admission.save()
                    processed.append({'formKey': form_key, 'admission_id': admission.id})
                else:
                    failed.append({'formKey': form_key, 'error': form.errors})
            except Exception as exc:
                failed.append({'formKey': form_key, 'error': str(exc)})
        elif action_type == 'schedule_follow_up':
            try:
                patient_id = data.get('patient_id') or data.get('patient')
                if not patient_id:
                    raise ValueError('No patient selected')
                patient = Patient.objects.get(patient_id=patient_id)
                form = FollowUpForm(data)
                if form.is_valid():
                    follow_up = form.save(commit=False)
                    follow_up.patient = patient
                    follow_up.created_by = request.user
                    follow_up.save()
                    processed.append({'formKey': form_key, 'follow_up_id': follow_up.id})
                else:
                    failed.append({'formKey': form_key, 'error': form.errors})
            except Exception as exc:
                failed.append({'formKey': form_key, 'error': str(exc)})
        elif action_type == 'create_bill':
            try:
                clinic_id = request.session.get('clinic_id')
                if not clinic_id:
                    raise ValueError('No clinic selected')
                clinic = Clinic.objects.get(id=clinic_id)
                patient_id = data.get('patient') or data.get('patient_id')
                if not patient_id:
                    raise ValueError('No patient selected')
                patient = Patient.objects.get(patient_id=patient_id, clinic_id=clinic_id)
                form = BillingForm(data, clinic_id=clinic_id)
                if form.is_valid():
                    bill = form.save(commit=False)
                    bill.created_by = request.user
                    bill.clinic = clinic
                    bill.patient = patient

                    appointment_id = data.get('appointment_id')
                    appointment_type = data.get('appointment_type')
                    if appointment_id and appointment_type:
                        if appointment_type == 'eye':
                            appointment_obj = EyeAppointment.objects.get(id=appointment_id, clinic_id=clinic_id)
                        else:
                            appointment_obj = Appointment.objects.get(id=appointment_id, clinic_id=clinic_id)
                        bill.appointment_object_id = appointment_obj.id
                        bill.appointment_content_type = ContentType.objects.get_for_model(appointment_obj)

                    selected_services = form.cleaned_data.get('services')
                    if selected_services:
                        bill.amount = sum(service.price for service in selected_services)
                    else:
                        bill.amount = form.cleaned_data.get('amount') or 0

                    if not bill.paid_amount:
                        bill.paid_amount = 0

                    if bill.discount_type != 'NONE' and bill.discount_value > 0:
                        bill.discount_applied_by = request.user
                        bill.discount_applied_at = timezone.now()

                    bill.calculate_final_amount()
                    effective_amount = bill.get_effective_amount()
                    if bill.paid_amount >= effective_amount and effective_amount > 0:
                        bill.status = 'PAID'
                    elif bill.paid_amount > 0:
                        bill.status = 'PARTIAL'
                    else:
                        bill.status = 'PENDING'

                    bill.save()
                    form.save_m2m()
                    processed.append({'formKey': form_key, 'billing_id': bill.id})
                else:
                    failed.append({'formKey': form_key, 'error': form.errors})
            except Exception as exc:
                failed.append({'formKey': form_key, 'error': str(exc)})
        elif action_type == 'record_payment':
            try:
                bill_id = data.get('bill_id') or data.get('billing_id')
                if not bill_id:
                    raise ValueError('No bill referenced')
                bill = Billing.objects.get(id=bill_id, clinic_id=request.session.get('clinic_id'))
                payment_amount = data.get('payment_amount') or data.get('amount')
                payment_amount = Decimal(str(payment_amount)) if payment_amount is not None else Decimal('0')

                if payment_amount <= 0:
                    raise ValueError('Payment amount must be greater than zero')

                effective_amount = bill.get_effective_amount()
                if payment_amount > (effective_amount - bill.paid_amount):
                    raise ValueError('Payment amount exceeds outstanding balance')

                with transaction.atomic():
                    bill.paid_amount += payment_amount
                    if bill.paid_amount >= effective_amount and effective_amount > 0:
                        bill.status = 'PAID'
                    elif bill.paid_amount > 0:
                        bill.status = 'PARTIAL'
                    else:
                        bill.status = 'PENDING'
                    bill.save()

                    Payment.objects.create(
                        billing=bill,
                        amount=payment_amount,
                        received_by=request.user,
                        payment_method=data.get('payment_method', 'CASH'),
                        transaction_reference=data.get('transaction_reference', ''),
                        notes=data.get('notes', '')
                    )

                processed.append({'formKey': form_key, 'billing_id': bill.id, 'payment_amount': str(payment_amount)})
            except Exception as exc:
                failed.append({'formKey': form_key, 'error': str(exc)})
        else:
            failed.append({'formKey': form_key, 'error': 'Unsupported action type'})

    return JsonResponse({'success': True, 'processed': processed, 'failed': failed})
