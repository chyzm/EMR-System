from decimal import Decimal
import json
import os
import uuid
import tempfile
from datetime import timedelta
from unittest.mock import Mock, patch
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import (
    Clinic, Patient, Billing, Payment, ServicePriceList, Notification,
    ServerSyncOutbox, ServerSyncState,
)
from core.server_sync import (
    apply_change,
    pull_remote_changes,
    push_pending_outbox,
    serialize_instance,
    sync_worker_lock,
)
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
