from decimal import Decimal
import json
import os
import uuid
import tempfile
from datetime import timedelta
from unittest.mock import Mock, patch
from django.contrib.auth import authenticate
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core import mail
from django.db import transaction
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from core.models import (
    Clinic, Patient, Billing, BillingLineItem, Payment, PaymentTransaction, PendingClinicRegistration, ServicePriceList, Notification, ActionLog,
    ServerSyncChange, ServerSyncOutbox, ServerSyncState, ClinicMedication, Prescription, StockMovement, PatientEncounter,
)
from django.contrib.auth.hashers import make_password
from core.utils import log_action
from core.server_sync import (
    apply_change,
    pull_remote_changes,
    push_pending_outbox,
    serialize_instance,
    sync_worker_lock,
)
from core.payments import PaymentVerificationError, confirm_paystack_payment
from DurielMedicApp.models import Admission, Appointment, FollowUp, NurseInstruction, PhysiotherapyReferral, Vitals


@override_settings(SECURE_SSL_REDIRECT=False, PAYSTACK_SECRET_KEY='sk_test_secret')
class SubscriptionPaymentTests(TestCase):
    def paystack_success(self, payment, *, amount=None, currency='NGN'):
        response = Mock()
        response.json.return_value = {
            'status': True,
            'data': {
                'status': 'success',
                'reference': payment.reference,
                'amount': amount if amount is not None else int(payment.amount * 100),
                'currency': currency,
            },
        }
        return response

    def test_confirm_registration_payment_creates_clinic_once(self):
        payment = PaymentTransaction.objects.create(
            reference='DM-REG-001',
            email='owner@example.com',
            plan_type='MONTHLY',
            amount=Decimal('15000.00'),
        )
        PendingClinicRegistration.objects.create(
            payment=payment,
            clinic_name='Grace Clinic',
            clinic_type='GENERAL',
            clinic_address='1 Test Street',
            clinic_phone='08000000000',
            clinic_email='clinic@example.com',
            username='owner',
            email='owner@example.com',
            password_hash=make_password('secret123'),
            expires_at=timezone.now() + timedelta(hours=1),
        )

        with patch('core.payments.requests.get', return_value=self.paystack_success(payment)):
            confirmed = confirm_paystack_payment(payment.reference)
            confirm_paystack_payment(payment.reference)

        self.assertEqual(confirmed.status, 'PAID')
        self.assertEqual(Clinic.objects.count(), 1)
        self.assertEqual(get_user_model().objects.count(), 1)
        clinic = Clinic.objects.get()
        self.assertTrue(clinic.is_subscription_active)
        self.assertEqual(clinic.subscription_type, 'MONTHLY')

    def test_confirm_renewal_payment_extends_once(self):
        clinic = Clinic.objects.create(
            name='Renew Clinic',
            clinic_type='GENERAL',
            address='123 Main',
            phone='08000000000',
            email='clinic@example.com',
            subscription_type='MONTHLY',
            subscription_start_date=timezone.localdate(),
            subscription_end_date=timezone.localdate() + timedelta(days=10),
            is_subscription_active=True,
        )
        payment = PaymentTransaction.objects.create(
            reference='DM-REN-001',
            clinic=clinic,
            email='clinic@example.com',
            plan_type='MONTHLY',
            amount=Decimal('15000.00'),
        )

        with patch('core.payments.requests.get', return_value=self.paystack_success(payment)):
            confirm_paystack_payment(payment.reference)
            clinic.refresh_from_db()
            first_end = clinic.subscription_end_date
            confirm_paystack_payment(payment.reference)
            clinic.refresh_from_db()

        self.assertEqual(clinic.subscription_end_date, first_end)
        self.assertEqual(PaymentTransaction.objects.get(pk=payment.pk).status, 'PAID')

    def test_amount_mismatch_is_rejected(self):
        payment = PaymentTransaction.objects.create(
            reference='DM-BAD-AMOUNT',
            email='owner@example.com',
            plan_type='MONTHLY',
            amount=Decimal('15000.00'),
        )

        with patch('core.payments.requests.get', return_value=self.paystack_success(payment, amount=1)):
            with self.assertRaises(PaymentVerificationError):
                confirm_paystack_payment(payment.reference)

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'FAILED')
        self.assertEqual(Clinic.objects.count(), 0)

    def test_currency_mismatch_is_rejected(self):
        payment = PaymentTransaction.objects.create(
            reference='DM-BAD-CURRENCY',
            email='owner@example.com',
            plan_type='YEARLY',
            amount=Decimal('150000.00'),
        )

        with patch('core.payments.requests.get', return_value=self.paystack_success(payment, currency='USD')):
            with self.assertRaises(PaymentVerificationError):
                confirm_paystack_payment(payment.reference)

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'FAILED')

    def test_webhook_rejects_invalid_signature(self):
        response = self.client.post(
            reverse('core:paystack_webhook'),
            data=json.dumps({'event': 'charge.success'}),
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE='bad',
        )

        self.assertEqual(response.status_code, 400)

    @override_settings(SYNC_SERVER_ROLE='central')
    def test_subscription_renewal_creates_sync_change_payload(self):
        clinic = Clinic.objects.create(
            name='Sync Renewal Clinic',
            clinic_type='GENERAL',
            address='123 Main',
            phone='08000000000',
            email='clinic@example.com',
        )
        ServerSyncChange.objects.all().delete()

        clinic.set_subscription('MONTHLY')

        change = ServerSyncChange.objects.filter(
            model_label='core.Clinic',
            record_sync_id=clinic.sync_id,
        ).latest('id')
        self.assertEqual(change.payload['subscription_type'], 'MONTHLY')
        self.assertIsNotNone(change.payload['subscription_start_date'])
        self.assertIsNotNone(change.payload['subscription_end_date'])
        self.assertTrue(change.payload['is_subscription_active'])
        self.assertEqual(change.payload['last_reminder_sent'], 'NONE')


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

    def test_cloud_appointment_edit_preserves_provider_and_saves(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            provider=self.user,
            clinic=self.clinic,
            payment_type='SELF',
            date=timezone.localdate() + timedelta(days=2),
            start_time='09:00',
            end_time='09:30',
            reason='Initial reason',
            status='SCHEDULED',
        )

        edit_url = reverse('DurielMedicApp:appointment_update', args=[appointment.pk])
        get_response = self.client.get(edit_url)
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(str(get_response.context['form']['provider'].value()), str(self.user.pk))

        response = self.client.post(edit_url, {
            'patient': self.patient.pk,
            'provider': self.user.pk,
            'date': appointment.date.isoformat(),
            'start_time': '09:00',
            'end_time': '09:30',
            'reason': 'Updated in cloud',
            'notes': 'Saved normally',
            'payment_type': 'SELF',
        })

        self.assertRedirects(response, reverse('DurielMedicApp:appointment_list'), fetch_redirect_response=False)
        appointment.refresh_from_db()
        self.assertEqual(appointment.reason, 'Updated in cloud')

    def test_existing_past_appointment_can_be_edited_without_changing_date(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            provider=self.user,
            clinic=self.clinic,
            payment_type='SELF',
            date=timezone.localdate() - timedelta(days=2),
            start_time='09:00',
            end_time='09:30',
            reason='Historical appointment',
            status='COMPLETED',
        )

        response = self.client.post(reverse('DurielMedicApp:appointment_update', args=[appointment.pk]), {
            'patient': self.patient.pk,
            'provider': self.user.pk,
            'date': appointment.date.isoformat(),
            'start_time': '09:00',
            'end_time': '09:30',
            'reason': 'Corrected historical note',
            'notes': '',
            'payment_type': 'SELF',
        })

        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.reason, 'Corrected historical note')

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

    def activate_local_sync(self):
        ServerSyncState.objects.update_or_create(
            key='local_server',
            defaults={'value': {
                'activated': True,
                'central_url': 'https://cloud.example',
                'sync_token': 'test-token',
                'clinic_sync_id': str(self.clinic.sync_id),
                'node_id': 'test-local-node',
            }},
        )

    def test_local_patient_edit_is_queued_and_pushed_to_cloud(self):
        self.activate_local_sync()
        self.patient.email = 'jd@duck.com.ng'
        self.patient.save(update_fields=['email', 'updated_at'])

        queued = ServerSyncOutbox.objects.get(record_sync_id=self.patient.sync_id)
        self.assertEqual(queued.payload['email'], 'jd@duck.com.ng')

        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {'processed': [str(queued.operation_id)], 'failed': []}
        with patch('core.server_sync.requests.post', return_value=response) as request_post:
            result = push_pending_outbox()

        self.assertEqual(result, {'processed': 1, 'failed': 0})
        sent_item = request_post.call_args.kwargs['json']['items'][0]
        self.assertEqual(sent_item['payload']['email'], 'jd@duck.com.ng')

    def test_notification_is_bidirectionally_syncable(self):
        self.activate_local_sync()
        notification = Notification.objects.create(clinic=self.clinic, message='New appointment')
        self.assertTrue(ServerSyncOutbox.objects.filter(record_sync_id=notification.sync_id).exists())

    def test_sync_worker_lock_prevents_overlapping_workers(self):
        with tempfile.TemporaryDirectory() as runtime_root, patch.dict(
            os.environ,
            {'DURIELMEDIC_RUNTIME_DIR': runtime_root},
        ):
            with sync_worker_lock() as first_worker:
                self.assertTrue(first_worker)
                with sync_worker_lock() as second_worker:
                    self.assertFalse(second_worker)
            with sync_worker_lock() as next_pass:
                self.assertTrue(next_pass)

    def test_local_update_config_exposes_manifest_without_sync_secret(self):
        self.activate_local_sync()
        state = ServerSyncState.objects.get(key='local_server')
        state.value['update_manifest_url'] = 'https://cloud.example/releases/update-manifest.json'
        state.save(update_fields=['value', 'updated_at'])

        with tempfile.TemporaryDirectory() as output_dir:
            output_path = os.path.join(output_dir, 'update-config.json')
            call_command('local_update_config', '--output', output_path)
            with open(output_path, encoding='utf-8') as config_file:
                payload = json.load(config_file)

        self.assertTrue(payload['activated'])
        self.assertEqual(payload['role'], 'local')
        self.assertEqual(payload['update_manifest_url'], 'https://cloud.example/releases/update-manifest.json')
        self.assertNotIn('sync_token', payload)

    def test_partial_bootstrap_records_version_and_advances_next_page(self):
        self.activate_local_sync()
        ServerSyncState.objects.update_or_create(
            key='central_pull_cursor',
            defaults={'value': {
                'cursor': 0,
                'bootstrap_done': False,
                'bootstrap_offset': 25,
                'bootstrap_version': 0,
            }},
        )
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            'changes': [],
            'users': [],
            'nextCursor': 0,
            'bootstrapDone': False,
            'nextBootstrapOffset': 25,
            'hasMore': True,
        }

        with patch('core.server_sync.requests.get', return_value=response) as request_get:
            first = pull_remote_changes()
            second = pull_remote_changes()

        self.assertTrue(first['has_more'])
        self.assertEqual(request_get.call_args_list[0].kwargs['params']['bootstrap_offset'], 0)
        self.assertEqual(request_get.call_args_list[1].kwargs['params']['bootstrap_offset'], 25)
        state = ServerSyncState.objects.get(key='central_pull_cursor').value
        self.assertEqual(state['bootstrap_version'], 3)

    def test_patient_profile_picture_payload_contains_and_restores_file(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            self.patient.profile_picture = SimpleUploadedFile('avatar.png', b'fake-png-content', content_type='image/png')
            self.patient.save()
            payload = serialize_instance(self.patient)
            self.assertEqual(payload['profile_picture']['name'], 'patient_profiles/avatar.png')
            self.assertTrue(payload['profile_picture']['content_b64'])

            self.patient.profile_picture.delete(save=False)
            self.patient.profile_picture = ''
            self.patient.save(update_fields=['profile_picture'])
            apply_change({
                'operation_id': str(uuid.uuid4()),
                'model_label': 'core.Patient',
                'action': 'update',
                'record_sync_id': str(self.patient.sync_id),
                'payload': payload,
            }, origin_node_id='central')
            self.patient.refresh_from_db()
            self.assertTrue(self.patient.profile_picture.storage.exists(self.patient.profile_picture.name))

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

    def test_select_clinic_shows_remaining_days_and_early_renewal(self):
        response = self.client.get(reverse('core:select_clinic'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '30 days remaining')
        self.assertContains(response, 'Renew early without losing remaining days')
        self.assertContains(response, 'Add 30 days')

    def test_renewal_extends_existing_admin_or_paystack_expiry(self):
        original_end = timezone.now().date() + timedelta(days=12)
        self.clinic.subscription_end_date = original_end
        self.clinic.is_subscription_active = True
        self.clinic.save(update_fields=['subscription_end_date', 'is_subscription_active'])

        self.clinic.set_subscription('MONTHLY')

        self.assertEqual(self.clinic.subscription_end_date, original_end + timedelta(days=30))
        self.assertTrue(self.clinic.is_subscription_active)

    def test_select_clinic_uses_expired_wording_after_expiry(self):
        self.clinic.subscription_end_date = timezone.now().date() - timedelta(days=1)
        self.clinic.is_subscription_active = False
        self.clinic.save(update_fields=['subscription_end_date', 'is_subscription_active'])

        response = self.client.get(reverse('core:select_clinic'))

        self.assertContains(response, 'Expired:')
        self.assertNotContains(response, 'days remaining')

    def test_service_worker_is_served_at_root_scope(self):
        response = self.client.get(reverse('core:service_worker'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertIn('durielmedic-pages-v5', response.content.decode('utf-8'))


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class OperationalHealthTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='root',
            email='root@example.com',
            password='secret123',
            role='ADMIN',
        )
        self.clinic = Clinic.objects.create(
            name='Operational Clinic',
            clinic_type='GENERAL',
            address='1 Ops Road',
            phone='08000000000',
            email='ops@example.com',
            subscription_type='MONTHLY',
            subscription_start_date=timezone.localdate(),
            subscription_end_date=timezone.localdate() + timedelta(days=30),
            is_subscription_active=True,
        )
        self.superuser.clinic.add(self.clinic)

    def test_logs_healthcheck_reports_action_log_status(self):
        response = self.client.get(reverse('core:logs_healthcheck'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['checks']['action_log_query'], 'ok')
        self.assertIn('count', data['logs'])

    def test_superuser_actions_are_audited(self):
        request = Mock()
        request.user = self.superuser
        request.session = {'clinic_id': self.clinic.id}

        log_action(request, 'UPDATE', self.clinic, details='Superuser audit test')

        self.assertTrue(
            ActionLog.objects.filter(
                user=self.superuser,
                clinic=self.clinic,
                action='UPDATE',
                details='Superuser audit test',
            ).exists()
        )


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class BillingAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(username='billing-admin', email='billing-admin@example.com', password='secret', role='ADMIN')
        self.receptionist = User.objects.create_user(username='billing-frontdesk', email='billing-frontdesk@example.com', password='secret', role='RECEPTIONIST')
        self.doctor = User.objects.create_user(username='billing-doctor', email='billing-doctor@example.com', password='secret', role='DOCTOR')
        self.dentist = User.objects.create_user(username='billing-dentist', email='billing-dentist@example.com', password='secret', role='DENTIST')
        self.clinic = Clinic.objects.create(
            name='Billing Clinic',
            clinic_type='GENERAL',
            address='1 Billing Road',
            phone='08000000000',
            email='billing@example.com',
            subscription_type='MONTHLY',
            subscription_start_date=timezone.localdate(),
            subscription_end_date=timezone.localdate() + timedelta(days=30),
            is_subscription_active=True,
        )
        self.other_clinic = Clinic.objects.create(
            name='Other Billing Clinic',
            clinic_type='GENERAL',
            address='2 Billing Road',
            phone='08000000001',
            email='otherbilling@example.com',
            subscription_type='MONTHLY',
            subscription_start_date=timezone.localdate(),
            subscription_end_date=timezone.localdate() + timedelta(days=30),
            is_subscription_active=True,
        )
        for user in (self.admin, self.receptionist, self.doctor, self.dentist):
            user.clinic.add(self.clinic)
        self.patient = Patient.objects.create(
            clinic=self.clinic,
            first_name='Bill',
            last_name='Patient',
            date_of_birth='1990-01-01',
            gender='F',
            allergies='None',
            contact='08012345678',
            address='Billing Address',
            emergency_contact='08087654321',
            created_by=self.admin,
        )
        self.other_patient = Patient.objects.create(
            clinic=self.other_clinic,
            patient_id='TENANTB001',
            first_name='Other',
            last_name='Patient',
            date_of_birth='1990-01-01',
            gender='M',
            allergies='None',
            contact='08012345679',
            address='Other Address',
            emergency_contact='08087654322',
            created_by=self.admin,
        )
        self.bill = Billing.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            service_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=7),
            amount=Decimal('1000.00'),
            paid_amount=Decimal('0.00'),
            description='Consultation',
        )
        self.other_bill = Billing.objects.create(
            patient=self.other_patient,
            clinic=self.other_clinic,
            service_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=7),
            amount=Decimal('1000.00'),
            paid_amount=Decimal('0.00'),
            description='Other consultation',
        )

    def select_clinic_as(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['clinic_id'] = self.clinic.id
        session['clinic_type'] = self.clinic.clinic_type
        session['clinic_name'] = self.clinic.name
        session.save()

    def select_clinic(self):
        session = self.client.session
        session['clinic_id'] = self.clinic.id
        session['clinic_type'] = self.clinic.clinic_type
        session['clinic_name'] = self.clinic.name
        session.save()

    def test_admin_and_receptionist_can_open_billing(self):
        for user in (self.admin, self.receptionist):
            self.select_clinic_as(user)
            response = self.client.get(reverse('core:billing_list'))
            self.assertEqual(response.status_code, 200)
            response = self.client.get(reverse('core:view_bill', args=[self.bill.pk]))
            self.assertEqual(response.status_code, 200)

    def test_create_bill_shows_patient_activity_handoff(self):
        self.select_clinic_as(self.admin)
        response = self.client.get(f"{reverse('core:create_bill')}?patient={self.patient.patient_id}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recent Patient Activity for Billing')

    def test_report_dashboard_renders_business_sections_and_chat(self):
        self.select_clinic_as(self.admin)
        response = self.client.get(reverse('DurielMedicApp:generate_report'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reports & Business Intelligence')
        self.assertContains(response, 'Needs Attention')
        self.assertContains(response, 'Service Performance')
        self.assertContains(response, 'Charts')
        self.assertNotContains(response, 'Report Chat')

    def test_billing_queue_merges_items_from_same_appointment_flow(self):
        self.select_clinic_as(self.admin)
        appointment = Appointment.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            provider=self.doctor,
            date=timezone.localdate(),
            start_time='09:00',
            end_time='09:30',
            reason='Queue grouping',
            status='COMPLETED',
        )
        appointment_ct = ContentType.objects.get_for_model(appointment)
        encounter = PatientEncounter.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            provider=self.doctor,
            encounter_type='GENERAL_CONSULTATION',
            status='COMPLETED',
            appointment_content_type=appointment_ct,
            appointment_object_id=appointment.pk,
            created_by=self.doctor,
        )
        BillingLineItem.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            appointment_content_type=appointment_ct,
            appointment_object_id=appointment.pk,
            source_type='CONSULTATION',
            description='Consultation',
            quantity=1,
            unit_price=0,
            status='APPROVED',
            created_by=self.doctor,
        )
        BillingLineItem.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            encounter=encounter,
            source_type='LAB',
            description='FBC',
            quantity=1,
            unit_price=Decimal('2500.00'),
            status='APPROVED',
            created_by=self.doctor,
        )

        response = self.client.get(reverse('core:billing_list'))

        self.assertEqual(response.status_code, 200)
        groups = response.context['due_billing_groups']
        matching_groups = [
            group for group in groups
            if group['patient'] == self.patient and group.get('appointment') == appointment
        ]
        self.assertEqual(len(matching_groups), 1)
        self.assertEqual(len(matching_groups[0]['items']), 1)
        self.assertContains(response, 'FBC')

    def test_admin_can_deactivate_billing_queue_entry(self):
        self.select_clinic_as(self.admin)
        item = BillingLineItem.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            source_type='PRESCRIPTION',
            description='Paracetamol (500mg) (12)',
            quantity=12,
            unit_price=Decimal('100.00'),
            status='APPROVED',
            created_by=self.doctor,
        )

        response = self.client.post(reverse('core:deactivate_billing_queue'), {
            'line_items': str(item.pk),
        })

        self.assertRedirects(response, reverse('core:billing_list'), fetch_redirect_response=False)
        item.refresh_from_db()
        self.assertEqual(item.status, 'VOIDED')
        self.assertTrue(ActionLog.objects.filter(details__icontains='Voided 1 billing queue item').exists())

    def test_receptionist_cannot_deactivate_billing_queue_entry(self):
        self.select_clinic_as(self.receptionist)
        item = BillingLineItem.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            source_type='PRESCRIPTION',
            description='Amatem Forte Softgel (6)',
            quantity=6,
            unit_price=Decimal('166.67'),
            status='APPROVED',
            created_by=self.doctor,
        )

        response = self.client.post(reverse('core:deactivate_billing_queue'), {
            'line_items': str(item.pk),
        })

        self.assertIn(response.status_code, (302, 403))
        item.refresh_from_db()
        self.assertEqual(item.status, 'APPROVED')

    def test_receipt_hides_staff_user_id_and_exposes_email_and_thermal_actions(self):
        self.select_clinic_as(self.admin)
        Payment.objects.create(
            billing=self.bill,
            amount=Decimal('500.00'),
            payment_method='CASH',
            received_by=self.admin,
        )

        response = self.client.get(reverse('core:generate_receipt', args=[self.bill.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'User ID:')
        self.assertContains(response, 'Email Patient')
        self.assertContains(response, '80mm Print')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_receipt_email_is_sent_to_billed_patient(self):
        self.select_clinic_as(self.admin)
        self.patient.email = 'patient@example.com'
        self.patient.save(update_fields=['email'])
        Payment.objects.create(
            billing=self.bill,
            amount=Decimal('500.00'),
            payment_method='CASH',
            received_by=self.admin,
        )

        response = self.client.post(reverse('core:email_receipt', args=[self.bill.pk]))

        self.assertRedirects(response, reverse('core:generate_receipt', args=[self.bill.pk]), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['patient@example.com'])
        self.assertIn(self.clinic.name, mail.outbox[0].body)

    def test_clinical_roles_cannot_open_billing_urls(self):
        for user in (self.doctor, self.dentist):
            self.select_clinic_as(user)
            for url_name, args in (
                ('core:billing_list', []),
                ('core:view_bill', [self.bill.pk]),
                ('core:record_payment', [self.bill.pk]),
                ('core:edit_bill', [self.bill.pk]),
                ('core:delete_bill', [self.bill.pk]),
                ('core:generate_receipt', [self.bill.pk]),
            ):
                response = self.client.get(reverse(url_name, args=args))
                self.assertIn(response.status_code, (302, 403), url_name)
                if response.status_code == 302:
                    self.assertIn(reverse('core:clinic_dashboard'), response['Location'])

    def test_billing_detail_urls_are_scoped_to_selected_clinic(self):
        self.select_clinic_as(self.admin)
        for url_name in (
            'core:view_bill',
            'core:record_payment',
            'core:edit_bill',
            'core:delete_bill',
            'core:generate_receipt',
        ):
            response = self.client.get(reverse(url_name, args=[self.other_bill.pk]))
            self.assertEqual(response.status_code, 404, url_name)


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class PrescriptionReconciliationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.clinic = Clinic.objects.create(
            name='Pharmacy Clinic',
            clinic_type='GENERAL',
            address='123 Main',
            phone='08000000000',
            email='pharmacy@example.com',
            subscription_type='MONTHLY',
            subscription_start_date=timezone.now().date(),
            subscription_end_date=timezone.now().date() + timedelta(days=30),
            is_subscription_active=True,
        )
        self.pharmacist = User.objects.create_user(username='pharm', password='secret', role='PHARMACIST')
        self.doctor = User.objects.create_user(username='rxdoctor', password='secret', role='DOCTOR')
        self.pharmacist.clinic.add(self.clinic)
        self.doctor.clinic.add(self.clinic)
        self.patient = Patient.objects.create(
            clinic=self.clinic,
            first_name='Uche',
            last_name='Okaro',
            date_of_birth='1990-01-01',
            gender='M',
            blood_group='O+',
            contact='08012345678',
            address='Test Address',
            emergency_contact='08087654321',
            created_by=self.doctor,
        )
        self.medication = ClinicMedication.objects.create(
            clinic=self.clinic,
            name='Paracetamol',
            strength='500mg',
            quantity_in_stock=5,
            minimum_stock_level=2,
            selling_price=Decimal('700.00'),
            added_by=self.pharmacist,
        )
        self.prescription = Prescription.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            prescribed_by=self.doctor,
            clinic_medication=self.medication,
            dosage='500mg',
            frequency='bd',
            duration='3 days',
            quantity_prescribed=1,
            stock_deducted=True,
        )
        self.client.force_login(self.pharmacist)
        session = self.client.session
        session['clinic_id'] = self.clinic.id
        session['clinic_type'] = self.clinic.clinic_type
        session['clinic_name'] = self.clinic.name
        session.save()

    def test_reconcile_dispensed_prescription_restores_stock_credits_bill_and_logs(self):
        response = self.client.post(reverse('core:reconcile_prescription', args=[self.prescription.pk]), {
            'reconcile_type': 'RETURNED',
            'reason': 'Patient returned unopened medication.',
        })

        self.assertRedirects(response, reverse('core:prescription_list'), fetch_redirect_response=False)
        self.prescription.refresh_from_db()
        self.medication.refresh_from_db()
        self.assertFalse(self.prescription.stock_deducted)
        self.assertEqual(self.medication.quantity_in_stock, 6)
        self.assertTrue(StockMovement.objects.filter(
            medication=self.medication,
            movement_type='IN',
            quantity=1,
            reference__contains='reconciliation',
        ).exists())
        self.assertTrue(Billing.objects.filter(
            patient=self.patient,
            amount=Decimal('-700.00'),
            description__icontains='Medication reconciliation credit',
        ).exists())
        self.assertTrue(ActionLog.objects.filter(
            action='UPDATE',
            details__icontains='Patient returned unopened medication.',
        ).exists())


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class MultiTenantIsolationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.clinic = Clinic.objects.create(
            name='Alpha Clinic',
            clinic_type='GENERAL',
            address='1 Tenant A',
            phone='08000000000',
            email='a@example.com',
            subscription_type='MONTHLY',
            subscription_start_date=timezone.localdate(),
            subscription_end_date=timezone.localdate() + timedelta(days=30),
            is_subscription_active=True,
        )
        self.other_clinic = Clinic.objects.create(
            name='Beta Clinic',
            clinic_type='GENERAL',
            address='1 Tenant B',
            phone='08000000001',
            email='b@example.com',
            subscription_type='MONTHLY',
            subscription_start_date=timezone.localdate(),
            subscription_end_date=timezone.localdate() + timedelta(days=30),
            is_subscription_active=True,
        )
        self.user = User.objects.create_user(username='tenant-a-doctor', password='secret', role='DOCTOR')
        self.user.clinic.add(self.clinic)
        self.patient = Patient.objects.create(
            clinic=self.clinic,
            first_name='Ada',
            last_name='Tenant',
            date_of_birth='1990-01-01',
            gender='F',
            allergies='None',
            contact='08012345678',
            address='Tenant A Address',
            emergency_contact='08087654321',
            created_by=self.user,
        )
        self.other_patient = Patient.objects.create(
            clinic=self.other_clinic,
            first_name='Other',
            last_name='Patient',
            date_of_birth='1990-01-01',
            gender='M',
            allergies='None',
            contact='08012345679',
            address='Tenant B Address',
            emergency_contact='08087654322',
            created_by=self.user,
        )
        self.other_appointment = Appointment.objects.create(
            patient=self.other_patient,
            provider=self.user,
            clinic=self.other_clinic,
            payment_type='SELF',
            date=timezone.localdate(),
            start_time='09:00',
            end_time='09:30',
            reason='Other clinic appointment',
            status='SCHEDULED',
        )
        self.client.force_login(self.user)
        session = self.client.session
        session['clinic_id'] = self.clinic.id
        session['clinic_type'] = self.clinic.clinic_type
        session['clinic_name'] = self.clinic.name
        session.save()

    def test_patient_detail_blocks_other_clinic_patient(self):
        response = self.client.get(reverse('core:patient_detail', args=[self.other_patient.patient_id]))
        self.assertEqual(response.status_code, 404)

    def test_general_appointment_detail_blocks_other_clinic_appointment(self):
        response = self.client.get(reverse('DurielMedicApp:appointment_detail', args=[self.other_appointment.pk]))
        self.assertEqual(response.status_code, 404)

    def test_patient_search_is_scoped_to_selected_clinic(self):
        response = self.client.get(reverse('core:patient_search_api'), {'q': 'Patient'})
        self.assertEqual(response.status_code, 200)
        names = [item['name'] for item in response.json()['results']]
        self.assertNotIn(self.other_patient.full_name, names)


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class WorkflowNotificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.clinic = Clinic.objects.create(
            name='Notify Clinic',
            clinic_type='GENERAL',
            address='1 Notify Road',
            phone='08000000000',
            email='notify@example.com',
            subscription_type='MONTHLY',
            subscription_start_date=timezone.localdate(),
            subscription_end_date=timezone.localdate() + timedelta(days=30),
            is_subscription_active=True,
        )
        self.receptionist = User.objects.create_user(username='notify-frontdesk', email='notify-frontdesk@example.com', password='secret', role='RECEPTIONIST')
        self.doctor = User.objects.create_user(username='notify-doctor', email='notify-doctor@example.com', password='secret', role='DOCTOR')
        self.nurse = User.objects.create_user(username='notify-nurse', email='notify-nurse@example.com', password='secret', role='NURSE')
        self.physiotherapist = User.objects.create_user(username='notify-physio', email='notify-physio@example.com', password='secret', role='PHYSIOTHERAPIST')
        for user in (self.receptionist, self.doctor, self.nurse, self.physiotherapist):
            user.clinic.add(self.clinic)
        self.patient = Patient.objects.create(
            clinic=self.clinic,
            first_name='Notify',
            last_name='Patient',
            date_of_birth='1990-01-01',
            gender='F',
            allergies='None',
            contact='08012345678',
            address='Notify Address',
            emergency_contact='08087654321',
            created_by=self.receptionist,
        )
        self.client.force_login(self.receptionist)
        session = self.client.session
        session['clinic_id'] = self.clinic.id
        session['clinic_type'] = self.clinic.clinic_type
        session['clinic_name'] = self.clinic.name
        session.save()

    def select_clinic(self):
        session = self.client.session
        session['clinic_id'] = self.clinic.id
        session['clinic_type'] = self.clinic.clinic_type
        session['clinic_name'] = self.clinic.name
        session.save()

    def test_general_appointment_creation_notifies_next_professionals(self):
        response = self.client.post(reverse('DurielMedicApp:appointment_create'), {
            'patient': self.patient.patient_id,
            'provider': self.doctor.pk,
            'date': (timezone.localdate() + timedelta(days=1)).isoformat(),
            'start_time': '09:00',
            'end_time': '09:30',
            'reason': 'Consultation',
            'notes': '',
            'payment_type': 'SELF',
        })

        self.assertRedirects(response, reverse('DurielMedicApp:appointment_list'), fetch_redirect_response=False)
        self.assertTrue(Notification.objects.filter(user=self.doctor, clinic=self.clinic, message__icontains='New general appointment').exists())
        self.assertTrue(Notification.objects.filter(user=self.nurse, clinic=self.clinic, message__icontains='New general appointment').exists())

    def test_vitals_queue_count_tracks_appointments_without_vitals(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            provider=self.doctor,
            date=timezone.localdate() + timedelta(days=1),
            start_time='10:00',
            end_time='10:30',
            reason='Vitals needed',
            status='SCHEDULED',
        )
        self.client.force_login(self.nurse)
        self.select_clinic()
        response = self.client.get(reverse('DurielMedicApp:vitals_queue_count'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)

        vitals = Vitals.objects.create(
            blood_pressure='120/80',
            pulse=78,
            temperature=37,
            weight=70,
            category='CONSULT',
        )
        vitals.set_appointment_object(appointment)
        vitals.save()
        response = self.client.get(reverse('DurielMedicApp:vitals_queue_count'))
        self.assertEqual(response.json()['count'], 0)

    def test_vitals_queue_renders_list_without_auto_opening_modal_state(self):
        Appointment.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            provider=self.doctor,
            date=timezone.localdate() + timedelta(days=1),
            start_time='10:00',
            end_time='10:30',
            reason='Vitals list',
            status='SCHEDULED',
        )
        self.client.force_login(self.nurse)
        self.select_clinic()

        response = self.client.get(reverse('DurielMedicApp:vitals_queue'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Vitals Queue')
        self.assertContains(response, 'x-data="{ vitalsOpen: false }"')
        self.assertContains(response, 'x-cloak')

    def test_doctor_instruction_queues_for_nurse_and_can_be_completed(self):
        self.client.force_login(self.doctor)
        self.select_clinic()
        response = self.client.post(reverse('DurielMedicApp:add_nurse_instruction', args=[self.patient.patient_id]), {
            'priority': 'URGENT',
            'instruction': 'Check blood pressure every 4 hours.',
        })
        self.assertRedirects(response, reverse('core:patient_detail', args=[self.patient.patient_id]), fetch_redirect_response=False)
        instruction = NurseInstruction.objects.get(patient=self.patient, clinic=self.clinic)
        self.assertEqual(instruction.status, 'OPEN')
        self.assertTrue(Notification.objects.filter(user=self.nurse, message__icontains='Nursing instruction').exists())

        self.client.force_login(self.nurse)
        self.select_clinic()
        response = self.client.get(reverse('DurielMedicApp:nurse_instruction_count'))
        self.assertEqual(response.json()['count'], 1)
        response = self.client.post(reverse('DurielMedicApp:complete_nurse_instruction', args=[instruction.pk]))
        self.assertRedirects(response, reverse('DurielMedicApp:nurse_instruction_queue'), fetch_redirect_response=False)
        instruction.refresh_from_db()
        self.assertEqual(instruction.status, 'DONE')
        self.assertEqual(instruction.completed_by, self.nurse)

    def test_physio_queue_count_tracks_assigned_referrals(self):
        PhysiotherapyReferral.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            referred_by=self.doctor,
            assigned_to=self.physiotherapist,
            reason='Mobility assessment',
        )
        self.client.force_login(self.physiotherapist)
        self.select_clinic()
        response = self.client.get(reverse('DurielMedicApp:physiotherapy_queue_count'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)

    def test_doctor_can_refer_appointment_to_physio_queue(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            provider=self.doctor,
            date=timezone.localdate(),
            start_time='14:00',
            end_time='14:30',
            reason='Back pain',
            status='SCHEDULED',
        )
        self.client.force_login(self.doctor)
        self.select_clinic()

        response = self.client.get(reverse('DurielMedicApp:appointment_detail', args=[appointment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Refer to Physio')

        response = self.client.post(
            f"{reverse('DurielMedicApp:refer_to_physiotherapy', args=[self.patient.patient_id])}?appointment_id={appointment.pk}",
            {
                'assigned_to': self.physiotherapist.pk,
                'priority': 'ROUTINE',
                'reason': 'Physiotherapy assessment needed',
                'notes': 'Assess gait and pain control.',
            },
        )
        self.assertRedirects(response, reverse('core:patient_detail', args=[self.patient.patient_id]), fetch_redirect_response=False)
        referral = PhysiotherapyReferral.objects.get(patient=self.patient, clinic=self.clinic)
        self.assertEqual(referral.appointment, appointment)
        self.assertEqual(referral.assigned_to, self.physiotherapist)

        self.client.force_login(self.physiotherapist)
        self.select_clinic()
        response = self.client.get(reverse('DurielMedicApp:physiotherapy_queue_count'))
        self.assertEqual(response.json()['count'], 1)

    def test_doctor_sees_physio_referral_in_appointment_actions(self):
        Appointment.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            provider=self.doctor,
            date=timezone.localdate(),
            start_time='16:00',
            end_time='16:30',
            reason='Appointment action referral',
            status='SCHEDULED',
        )
        self.client.force_login(self.doctor)
        self.select_clinic()

        response = self.client.get(reverse('DurielMedicApp:appointment_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Refer to Physio')

    def test_doctor_sees_physio_referral_button_on_completed_appointment(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            provider=self.doctor,
            date=timezone.localdate(),
            start_time='15:00',
            end_time='15:30',
            reason='Completed consultation needing physio',
            status='COMPLETED',
        )
        self.client.force_login(self.doctor)
        self.select_clinic()

        response = self.client.get(reverse('DurielMedicApp:appointment_detail', args=[appointment.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Refer to Physio')

    def test_finish_consultation_without_active_appointment_does_not_crash(self):
        self.patient.status = 'CONSULTATION_COMPLETE'
        self.patient.save(update_fields=['status'])
        self.client.force_login(self.doctor)
        self.select_clinic()

        response = self.client.get(reverse('DurielMedicApp:finish_consultation', args=[self.patient.patient_id]))

        self.assertRedirects(response, reverse('core:patient_detail', args=[self.patient.patient_id]), fetch_redirect_response=False)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.status, 'DISCHARGED')
        self.assertTrue(Notification.objects.filter(
            clinic=self.clinic,
            message__icontains=f"Consultation completed for {self.patient.full_name}",
        ).exists())

    def test_physio_queue_count_includes_direct_physio_appointments(self):
        Appointment.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            provider=self.physiotherapist,
            date=timezone.localdate() + timedelta(days=1),
            start_time='13:00',
            end_time='13:30',
            reason='Direct physiotherapy',
            status='SCHEDULED',
        )
        self.client.force_login(self.physiotherapist)
        self.select_clinic()
        response = self.client.get(reverse('DurielMedicApp:physiotherapy_queue_count'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)

    def test_direct_physio_appointment_completes_when_record_is_saved(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            provider=self.physiotherapist,
            date=timezone.localdate() + timedelta(days=1),
            start_time='14:00',
            end_time='14:30',
            reason='Direct physiotherapy record',
            status='SCHEDULED',
        )
        self.client.force_login(self.physiotherapist)
        self.select_clinic()
        response = self.client.post(
            f"{reverse('DurielMedicApp:add_physiotherapy_record', args=[self.patient.patient_id])}?appointment_id={appointment.pk}",
            {
                'appointment_id': appointment.pk,
                'chief_complaint': 'Back pain',
                'history_of_present_illness': '',
                'past_medical_history': '',
                'physical_examination': 'Reduced range of motion',
                'diagnosis': 'Lumbar strain',
                'treatment_goals': 'Pain control',
                'treatment_plan': 'Exercise therapy',
                'exercises_prescribed': '',
                'modalities_used': '',
                'progress_notes': '',
                'additional_notes': '',
            },
        )
        self.assertRedirects(response, reverse('DurielMedicApp:physiotherapy_queue'), fetch_redirect_response=False)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, 'COMPLETED')

    def test_physio_record_save_without_appointment_id_clears_assigned_queue_item(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            provider=self.physiotherapist,
            date=timezone.localdate() + timedelta(days=1),
            start_time='14:00',
            end_time='14:30',
            reason='Direct physiotherapy record',
            status='SCHEDULED',
        )
        self.client.force_login(self.physiotherapist)
        self.select_clinic()
        response = self.client.post(
            reverse('DurielMedicApp:add_physiotherapy_record', args=[self.patient.patient_id]),
            {
                'chief_complaint': 'Back pain',
                'history_of_present_illness': '',
                'past_medical_history': '',
                'physical_examination': 'Reduced range of motion',
                'diagnosis': 'Lumbar strain',
                'treatment_goals': 'Pain control',
                'treatment_plan': 'Exercise therapy',
                'exercises_prescribed': '',
                'modalities_used': '',
                'progress_notes': '',
                'additional_notes': '',
            },
        )
        self.assertRedirects(response, reverse('DurielMedicApp:physiotherapy_queue'), fetch_redirect_response=False)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, 'COMPLETED')
        response = self.client.get(reverse('DurielMedicApp:physiotherapy_queue_count'))
        self.assertEqual(response.json()['count'], 0)

    def test_complete_physio_consultation_action_clears_queue_count(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            provider=self.physiotherapist,
            date=timezone.localdate() + timedelta(days=1),
            start_time='15:00',
            end_time='15:30',
            reason='Physiotherapy review',
            status='SCHEDULED',
        )
        PhysiotherapyReferral.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            referred_by=self.doctor,
            assigned_to=self.physiotherapist,
            appointment=appointment,
            reason='Mobility assessment',
        )
        self.client.force_login(self.physiotherapist)
        self.select_clinic()
        response = self.client.post(reverse('DurielMedicApp:complete_physiotherapy_consultation', args=[appointment.pk]))
        self.assertRedirects(response, reverse('DurielMedicApp:physiotherapy_queue'), fetch_redirect_response=False)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, 'COMPLETED')
        self.assertFalse(PhysiotherapyReferral.objects.filter(status__in=['PENDING', 'ACCEPTED', 'IN_PROGRESS']).exists())
        response = self.client.get(reverse('DurielMedicApp:physiotherapy_queue_count'))
        self.assertEqual(response.json()['count'], 0)

    def test_appointment_can_target_physiotherapist(self):
        response = self.client.post(reverse('DurielMedicApp:appointment_create'), {
            'patient': self.patient.patient_id,
            'provider': self.physiotherapist.pk,
            'date': (timezone.localdate() + timedelta(days=1)).isoformat(),
            'start_time': '11:00',
            'end_time': '11:30',
            'reason': 'Physiotherapy',
            'notes': '',
            'payment_type': 'SELF',
        })
        self.assertRedirects(response, reverse('DurielMedicApp:appointment_list'), fetch_redirect_response=False)
        appointment = Appointment.objects.get(reason='Physiotherapy')
        self.assertEqual(appointment.provider, self.physiotherapist)
        self.assertTrue(Notification.objects.filter(user=self.physiotherapist, clinic=self.clinic, message__icontains='New general appointment').exists())

    def test_appointment_charge_items_roll_into_final_bill(self):
        service = ServicePriceList.objects.create(
            clinic=self.clinic,
            name='General Consultation',
            price=Decimal('5000.00'),
            is_active=True,
        )
        appointment = Appointment.objects.create(
            patient=self.patient,
            clinic=self.clinic,
            provider=self.doctor,
            date=timezone.localdate(),
            start_time='12:00',
            end_time='12:30',
            reason='Billing verification',
            status='COMPLETED',
        )
        url = f"{reverse('core:create_bill')}?patient={self.patient.patient_id}&appointment_id={appointment.pk}&appointment_type=general"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            BillingLineItem.objects.filter(
                patient=self.patient,
                clinic=self.clinic,
                source_type='CONSULTATION',
            ).exists()
        )
        self.assertContains(response, 'Consultation')

        response = self.client.post(reverse('core:create_bill'), {
            'patient': self.patient.patient_id,
            'appointment_id': appointment.pk,
            'appointment_type': 'general',
            'billing_line_items': [],
            'service_date': timezone.localdate().isoformat(),
            'due_date': (timezone.localdate() + timedelta(days=7)).isoformat(),
            'amount': '0',
            'paid_amount': '0',
            'description': '',
            'notes': 'Consultation',
            'discount_type': 'NONE',
            'discount_value': '0',
            'discount_reason': '',
        })
        self.assertEqual(response.status_code, 302)
        bill = Billing.objects.get(patient=self.patient, clinic=self.clinic, appointment_object_id=appointment.pk)
        self.assertEqual(bill.amount, Decimal('0.00'))
        self.assertEqual(bill.notes, 'Consultation')


class ClinicScopedUsernameTests(TestCase):
    def setUp(self):
        self.clinic_a = Clinic.objects.create(
            name='Tenant A',
            clinic_type='GENERAL',
            address='1 A Street',
            phone='08000000001',
            email='tenant-a@example.com',
            subscription_type='MONTHLY',
            subscription_start_date=timezone.localdate(),
            subscription_end_date=timezone.localdate() + timedelta(days=30),
            is_subscription_active=True,
        )
        self.clinic_b = Clinic.objects.create(
            name='Tenant B',
            clinic_type='EYE',
            address='1 B Street',
            phone='08000000002',
            email='tenant-b@example.com',
            subscription_type='MONTHLY',
            subscription_start_date=timezone.localdate(),
            subscription_end_date=timezone.localdate() + timedelta(days=30),
            is_subscription_active=True,
        )

    def create_staff(self, clinic, username, email):
        User = get_user_model()
        user = User.objects.create_user(
            username=username,
            email=email,
            password='secret',
            role='DOCTOR',
            primary_clinic=clinic,
            is_staff=True,
        )
        user.clinic.add(clinic)
        return user

    def test_same_username_allowed_across_clinics_with_unique_email(self):
        first = self.create_staff(self.clinic_a, 'frontdesk', 'frontdesk-a@example.com')
        second = self.create_staff(self.clinic_b, 'frontdesk', 'frontdesk-b@example.com')
        self.assertEqual(first.username, second.username)
        self.assertNotEqual(first.primary_clinic, second.primary_clinic)

    def test_same_username_blocked_inside_same_primary_clinic(self):
        self.create_staff(self.clinic_a, 'nurse', 'nurse-a@example.com')
        with self.assertRaises(Exception), transaction.atomic():
            self.create_staff(self.clinic_a, 'nurse', 'nurse-b@example.com')

    def test_email_is_globally_unique(self):
        self.create_staff(self.clinic_a, 'doctor-a', 'shared@example.com')
        with self.assertRaises(Exception), transaction.atomic():
            self.create_staff(self.clinic_b, 'doctor-b', 'shared@example.com')

    def test_duplicate_username_users_authenticate_by_email(self):
        first = self.create_staff(self.clinic_a, 'shareduser', 'shared-a@example.com')
        self.create_staff(self.clinic_b, 'shareduser', 'shared-b@example.com')
        self.assertIsNone(authenticate(username='shareduser', password='secret'))
        user = authenticate(username='shared-a@example.com', password='secret')
        self.assertEqual(user, first)
