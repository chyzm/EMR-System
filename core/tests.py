from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import Clinic, Patient, Billing, Payment, ServicePriceList
from DurielMedicApp.models import Admission, FollowUp


class SyncQueueTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='syncuser',
            email='sync@example.com',
            password='secret123',
            role='DOCTOR',
        )
        self.clinic = Clinic.objects.create(
            name='Test Clinic',
            clinic_type='GENERAL',
            address='123 Main',
            phone='08000000000',
            email='clinic@example.com',
        )
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
        response = self.client.post(
            reverse('core:sync_queue'),
            {
                'items': [{
                    'formKey': 'admission-1',
                    'action': 'admit_patient',
                    'payload': {
                        'patient_id': self.patient.patient_id,
                        'ward': 'Ward A',
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
        self.assertEqual(bill.amount, Decimal('1500.00'))
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
