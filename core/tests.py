from decimal import Decimal
import uuid
from datetime import timedelta
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import Clinic, Patient, Billing, Payment, ServicePriceList
from DurielMedicApp.models import Admission, Appointment, FollowUp


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class SyncQueueTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='syncuser',
            email='sync@example.com',
            password='secret123',
            role='ADMIN',
        )
        self.clinic = Clinic.objects.create(
            name='Test Clinic',
            clinic_type='GENERAL',
            address='123 Main',
            phone='08000000000',
            email='clinic@example.com',
            subscription_type='MONTHLY',
            subscription_start_date=timezone.now().date(),
            subscription_end_date=timezone.now().date() + timedelta(days=30),
            is_subscription_active=True,
        )
        self.user.clinic.add(self.clinic)
        self.client.force_login(self.user)
        session = self.client.session
        session['clinic_id'] = self.clinic.id
        session['clinic_type'] = self.clinic.clinic_type
        session.save()
        self.patient = Patient.objects.create(
            clinic=self.clinic,
            first_name='Ada',
            last_name='Lovelace',
            date_of_birth='1990-01-01',
            gender='F',
            blood_group='O+',
            allergies='None',
            contact='08012345678',
            address='Test Address',
            emergency_contact='08087654321',
            emergency_contact_name='Grace Hopper',
            created_by=self.user,
        )

    def test_sync_queue_creates_admission(self):
        self.client.force_login(self.user)
        self.patient.status = 'VITALS_TAKEN'
        self.patient.save(update_fields=['status'])
        response = self.client.post(
            reverse('core:sync_queue'),
            {
                'items': [{
                    'formKey': 'admission-1',
                    'action': 'admit_patient',
                    'payload': {
                        'patient_id': self.patient.patient_id,
                        'ward': 'Ward A',
                        'bed': 'Bed 1',
                        'admission_type': 'OBSERVATION',
                        'admission_source': 'OPD',
                        'provisional_diagnosis': 'Observation required',
                        'reason': 'Needs observation',
                    },
                }]
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(Admission.objects.count(), 1)
        admission = Admission.objects.get(patient=self.patient)
        self.assertEqual(admission.ward, 'Ward A')

    def test_sync_queue_creates_follow_up(self):
        self.client.force_login(self.user)
        self.patient.status = 'CONSULTATION_COMPLETE'
        self.patient.save(update_fields=['status'])
        response = self.client.post(
            reverse('core:sync_queue'),
            {
                'items': [{
                    'formKey': 'follow-up-1',
                    'action': 'schedule_follow_up',
                    'payload': {
                        'patient_id': self.patient.patient_id,
                        'reason': 'Routine review',
                        'scheduled_date': '2030-01-02',
                        'scheduled_time': '10:30:00',
                        'notes': 'Bring results',
                    },
                }]
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(FollowUp.objects.count(), 1)
        follow_up = FollowUp.objects.get(patient=self.patient)
        self.assertEqual(follow_up.reason, 'Routine review')

    def test_sync_queue_creates_bill(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['clinic_id'] = self.clinic.id
        session.save()

        service = ServicePriceList.objects.create(
            clinic=self.clinic,
            name='Consultation',
            price='1500.00',
            is_active=True,
        )

        response = self.client.post(
            reverse('core:sync_queue'),
            {
                'items': [{
                    'formKey': 'create-bill-1',
                    'action': 'create_bill',
                    'payload': {
                        'patient': self.patient.patient_id,
                        'service_date': '2030-01-01',
                        'due_date': '2030-02-01',
                        'amount': '1500.00',
                        'paid_amount': '0',
                        'description': 'Bill for consultation',
                        'discount_type': 'NONE',
                        'discount_value': '0',
                        'discount_reason': '',
                        'services': [str(service.id)],
                    },
                }]
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(Billing.objects.count(), 1)
        bill = Billing.objects.get(patient=self.patient)
        self.assertEqual(bill.amount, Decimal('3000.00'))
        self.assertEqual(bill.status, 'PENDING')

    def test_sync_queue_records_payment(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['clinic_id'] = self.clinic.id
        session.save()

        bill = Billing.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            service_date='2030-01-01',
            due_date='2030-02-01',
            amount='200.00',
            paid_amount='0',
            description='Test bill',
            discount_type='NONE',
            discount_value='0',
        )

        response = self.client.post(
            reverse('core:sync_queue'),
            {
                'items': [{
                    'formKey': 'record-payment-1',
                    'action': 'record_payment',
                    'payload': {
                        'bill_id': bill.id,
                        'payment_amount': '100.00',
                        'payment_method': 'CASH',
                    },
                }]
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        bill.refresh_from_db()
        self.assertEqual(bill.paid_amount, 100)
        self.assertEqual(bill.status, 'PARTIAL')
        self.assertEqual(Payment.objects.count(), 1)

    def test_sync_queue_is_idempotent_for_payments(self):
        bill = Billing.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            service_date='2030-01-01',
            due_date='2030-02-01',
            amount='200.00',
            paid_amount='0',
            description='Idempotency bill',
        )
        operation_id = str(uuid.uuid4())
        payload = {
            'items': [{
                'operationId': operation_id,
                'recordId': str(uuid.uuid4()),
                'formKey': 'idempotent-payment',
                'action': 'record_payment',
                'payload': {
                    '_billing_sync_id': str(bill.sync_id),
                    'payment_amount': '75.00',
                    'payment_method': 'CASH',
                },
            }],
        }

        first = self.client.post(reverse('core:sync_queue'), payload, content_type='application/json')
        second = self.client.post(reverse('core:sync_queue'), payload, content_type='application/json')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()['processed'][0]['duplicate'])
        bill.refresh_from_db()
        self.assertEqual(bill.paid_amount, Decimal('75.00'))
        self.assertEqual(Payment.objects.filter(billing=bill).count(), 1)

    def test_sync_queue_rejects_cross_tenant_patient(self):
        other_clinic = Clinic.objects.create(
            name='Other Clinic',
            clinic_type='GENERAL',
            address='Elsewhere',
            phone='08000000001',
            email='other@example.com',
        )
        other_patient = Patient.objects.create(
            clinic=other_clinic,
            first_name='Other',
            last_name='Patient',
            date_of_birth='1995-01-01',
            gender='F',
            allergies='None',
            contact='08012345679',
            address='Other Address',
            emergency_contact='08087654322',
            created_by=self.user,
        )

        response = self.client.post(
            reverse('core:sync_queue'),
            {
                'items': [{
                    'operationId': str(uuid.uuid4()),
                    'recordId': str(uuid.uuid4()),
                    'action': 'add_medical_record',
                    'payload': {
                        '_patient_sync_id': str(other_patient.sync_id),
                        'diagnosis': 'Should not cross tenants',
                    },
                }],
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['failed']), 1)
        self.assertEqual(other_patient.medical_records.count(), 0)

    def test_offline_bootstrap_is_scoped_to_active_clinic(self):
        other_clinic = Clinic.objects.create(
            name='Other Clinic',
            clinic_type='GENERAL',
            address='Elsewhere',
            phone='08000000001',
            email='other@example.com',
        )
        Patient.objects.create(
            clinic=other_clinic,
            first_name='Hidden',
            last_name='Patient',
            date_of_birth='1995-01-01',
            gender='M',
            allergies='None',
            contact='08012345679',
            address='Other Address',
            emergency_contact='08087654322',
            created_by=self.user,
        )

        response = self.client.get(reverse('core:offline_bootstrap'))

        self.assertEqual(response.status_code, 200)
        patient_ids = {patient['patient_id'] for patient in response.json()['patients']}
        self.assertEqual(patient_ids, {self.patient.patient_id})

    def test_syncs_local_patient_before_dependent_appointment(self):
        patient_sync_id = str(uuid.uuid4())
        appointment_sync_id = str(uuid.uuid4())
        response = self.client.post(
            reverse('core:sync_queue'),
            {
                'items': [
                    {
                        'operationId': str(uuid.uuid4()),
                        'recordId': patient_sync_id,
                        'action': 'patient_create',
                        'payload': {
                            'first_name': 'Offline',
                            'last_name': 'Patient',
                            'date_of_birth': '1992-01-01',
                            'gender': 'F',
                            'allergies': 'None',
                            'contact': '08022223333',
                            'address': 'Offline Address',
                            'emergency_contact': '08033334444',
                            'status': 'REGISTERED',
                        },
                    },
                    {
                        'operationId': str(uuid.uuid4()),
                        'recordId': appointment_sync_id,
                        'action': 'appointment_create',
                        'payload': {
                            '_patient_sync_id': patient_sync_id,
                            'provider': str(self.user.id),
                            'date': '2030-03-01',
                            'start_time': '09:00:00',
                            'end_time': '09:30:00',
                            'reason': 'Offline consultation',
                            'payment_type': 'SELF',
                        },
                    },
                ],
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['failed'], [])
        self.assertTrue(Patient.objects.filter(sync_id=patient_sync_id, clinic=self.clinic).exists())
        self.assertTrue(Appointment.objects.filter(sync_id=appointment_sync_id, clinic=self.clinic).exists())

    def test_expired_selected_clinic_is_blocked_after_session_exists(self):
        self.clinic.subscription_end_date = timezone.now().date() - timedelta(days=1)
        self.clinic.is_subscription_active = False
        self.clinic.save(update_fields=['subscription_end_date', 'is_subscription_active'])

        response = self.client.get(reverse('core:patient_list'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('core:select_clinic'), response['Location'])
        self.assertNotIn('clinic_id', self.client.session)

    def test_expired_selected_clinic_cannot_use_offline_bootstrap(self):
        self.clinic.subscription_end_date = timezone.now().date() - timedelta(days=1)
        self.clinic.is_subscription_active = False
        self.clinic.save(update_fields=['subscription_end_date', 'is_subscription_active'])

        response = self.client.get(reverse('core:offline_bootstrap'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('core:select_clinic'), response['Location'])

    def test_service_worker_is_served_at_root_scope(self):
        response = self.client.get(reverse('core:service_worker'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertIn('durielmedic-pages-v4', response.content.decode('utf-8'))
