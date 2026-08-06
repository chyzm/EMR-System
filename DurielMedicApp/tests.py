import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Billing, Clinic, ClinicMedication, Patient, Prescription, StockMovement
from core.server_sync import apply_change, serialize_instance
from core.sync import SERVER_SYNC_SNAPSHOT_MODELS
from DurielMedicApp.models import Admission, Appointment, MedicalRecord, MedicationAdministration


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class InpatientMedicationWorkflowTests(TestCase):
    def setUp(self):
        self.clinic = Clinic.objects.create(
            name='Ward Test Clinic',
            clinic_type='GENERAL',
            address='1 Clinic Road',
            phone='08000000000',
            email='ward@example.com',
            subscription_type='MONTHLY',
            subscription_start_date=timezone.localdate(),
            subscription_end_date=timezone.localdate() + timedelta(days=30),
            is_subscription_active=True,
        )
        User = get_user_model()
        self.doctor = User.objects.create_user(username='doctor', password='secret', role='DOCTOR')
        self.other_doctor = User.objects.create_user(username='doctor2', password='secret', role='DOCTOR')
        self.nurse = User.objects.create_user(username='nurse', password='secret', role='NURSE')
        for user in (self.doctor, self.other_doctor, self.nurse):
            user.clinic.add(self.clinic)
            user.primary_clinic = self.clinic
            user.save(update_fields=['primary_clinic'])
        self.patient = Patient.objects.create(
            clinic=self.clinic,
            first_name='Test',
            last_name='Patient',
            date_of_birth='1990-01-01',
            gender='F',
            allergies='None',
            contact='08011112222',
            address='Test Address',
            emergency_contact='08033334444',
            created_by=self.doctor,
        )
        self.admission = Admission.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            ward='Medical Ward',
            bed='B2',
            reason='Observation',
            attending_doctor=self.doctor,
            admitted_by=self.nurse,
        )
        self.medication = ClinicMedication.objects.create(
            clinic=self.clinic,
            name='Paracetamol',
            strength='500mg',
            quantity_in_stock=10,
            selling_price=Decimal('150.00'),
            added_by=self.doctor,
        )

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['clinic_id'] = self.clinic.id
        session['clinic_type'] = self.clinic.clinic_type
        session.save()

    def prescription_payload(self):
        return {
            'clinic_medication': self.medication.id,
            'dosage': '500mg',
            'frequency': 'Every 8 hours',
            'duration': '2 days',
            'quantity_prescribed': 3,
            'instructions': 'After food',
        }

    def test_doctor_can_prescribe_repeatedly_and_nurse_administration_bills_once(self):
        self.login(self.doctor)
        add_url = reverse('DurielMedicApp:add_admission_prescription', args=[self.admission.id])
        first_response = self.client.post(add_url, self.prescription_payload())
        second_response = self.client.post(add_url, self.prescription_payload())
        self.assertRedirects(first_response, reverse('DurielMedicApp:admission_detail', args=[self.admission.id]))
        self.assertRedirects(second_response, reverse('DurielMedicApp:admission_detail', args=[self.admission.id]))
        self.assertEqual(Prescription.objects.filter(admission=self.admission).count(), 2)

        prescription = Prescription.objects.filter(admission=self.admission).first()
        self.login(self.nurse)
        response = self.client.post(
            reverse('DurielMedicApp:record_medication_administration', args=[self.admission.id]),
            {
                'prescription': prescription.id,
                'quantity_administered': 1,
                'route': 'Oral',
                'administered_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
                'status': 'GIVEN',
                'notes': 'Tolerated',
            },
        )
        self.assertRedirects(response, reverse('DurielMedicApp:admission_detail', args=[self.admission.id]))
        administration = MedicationAdministration.objects.get(prescription=prescription)
        self.assertIsNotNone(administration.billing_id)
        self.assertEqual(Billing.objects.get(pk=administration.billing_id).amount, Decimal('150.00'))
        self.medication.refresh_from_db()
        self.assertEqual(self.medication.quantity_in_stock, 9)
        self.assertEqual(StockMovement.objects.filter(reference__contains=str(prescription.sync_id)).count(), 1)

    def test_prescription_can_only_be_deactivated_not_edited_or_deleted(self):
        prescription = Prescription.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            admission=self.admission,
            prescribed_by=self.doctor,
            clinic_medication=self.medication,
            dosage='500mg',
            frequency='Daily',
            duration='3 days',
            quantity_prescribed=3,
        )
        self.login(self.doctor)
        edit_response = self.client.post(reverse('core:edit_prescription', args=[prescription.id]), {'dosage': 'Changed'})
        delete_response = self.client.post(reverse('core:delete_prescription', args=[prescription.id]))
        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(delete_response.status_code, 302)
        prescription.refresh_from_db()
        self.assertEqual(prescription.dosage, '500mg')

        deactivate_response = self.client.post(reverse('core:deactivate_prescription', args=[prescription.id]))
        self.assertEqual(deactivate_response.status_code, 302)
        prescription.refresh_from_db()
        self.assertFalse(prescription.is_active)
        self.assertIsNotNone(prescription.deactivated_at)

    def test_every_doctor_sees_all_clinic_appointments(self):
        appointment = Appointment.objects.create(
            patient=self.patient, provider=self.other_doctor, clinic=self.clinic,
            date=timezone.localdate(), start_time='09:00', end_time='09:30',
            reason='Queued for another doctor', status='SCHEDULED',
        )
        self.login(self.doctor)
        response = self.client.get(reverse('DurielMedicApp:appointment_list'))
        self.assertIn(appointment, list(response.context['appointments']))

    def test_nurse_cannot_view_or_open_general_case_notes(self):
        record = MedicalRecord.objects.create(
            patient=self.patient,
            diagnosis='Confidential diagnosis',
            created_by=self.doctor,
        )
        self.login(self.nurse)
        detail = self.client.get(reverse('core:patient_detail', args=[self.patient.patient_id]))
        self.assertNotContains(detail, record.diagnosis)
        add_response = self.client.get(reverse('DurielMedicApp:add_medical_record', args=[self.patient.patient_id]))
        self.assertEqual(add_response.status_code, 302)

    def test_cloud_admission_payload_recreates_local_admission(self):
        payload = serialize_instance(self.admission)
        sync_id = self.admission.sync_id
        self.admission.delete()
        apply_change({
            'operation_id': str(uuid.uuid4()),
            'model_label': 'DurielMedicApp.Admission',
            'action': 'update',
            'record_sync_id': str(sync_id),
            'payload': payload,
        }, origin_node_id='central')
        restored = Admission.objects.get(sync_id=sync_id)
        self.assertEqual(restored.patient, self.patient)
        self.assertEqual(restored.clinic, self.clinic)
        self.assertEqual(restored.ward, 'Medical Ward')

    def test_bootstrap_orders_admission_before_prescription_and_administration(self):
        self.assertLess(SERVER_SYNC_SNAPSHOT_MODELS.index('DurielMedicApp.Admission'), SERVER_SYNC_SNAPSHOT_MODELS.index('core.Prescription'))
        self.assertLess(SERVER_SYNC_SNAPSHOT_MODELS.index('core.Prescription'), SERVER_SYNC_SNAPSHOT_MODELS.index('DurielMedicApp.MedicationAdministration'))
