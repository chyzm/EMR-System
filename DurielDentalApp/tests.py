from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Clinic, Notification, Patient
from DurielDentalApp.models import DentalAppointment


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class DentalRoleAccessTests(TestCase):
    def setUp(self):
        self.clinic = Clinic.objects.create(
            name='Dental Test Clinic',
            clinic_type='DENTAL',
            address='1 Dental Way',
            phone='08000000000',
            email='dental@example.com',
            subscription_type='MONTHLY',
            subscription_start_date=timezone.localdate(),
            subscription_end_date=timezone.localdate() + timedelta(days=30),
            is_subscription_active=True,
        )
        User = get_user_model()
        self.dentist = User.objects.create_user(username='dentist', password='secret', role='DENTIST')
        self.receptionist = User.objects.create_user(username='frontdesk', password='secret', role='RECEPTIONIST')
        for user in (self.dentist, self.receptionist):
            user.clinic.add(self.clinic)
            user.primary_clinic = self.clinic
            user.save(update_fields=['primary_clinic'])
        self.patient = Patient.objects.create(
            clinic=self.clinic,
            first_name='Dental',
            last_name='Patient',
            date_of_birth='1990-01-01',
            gender='F',
            contact='08011112222',
            address='Test Address',
            emergency_contact='08033334444',
            created_by=self.receptionist,
        )
        self.appointment = DentalAppointment.objects.create(
            patient=self.patient,
            provider=self.dentist,
            clinic=self.clinic,
            visit_type='CONSULTATION',
            payment_type='SELF',
            date=timezone.localdate() + timedelta(days=1),
            start_time='09:00',
            end_time='09:30',
            chief_complaint='Tooth pain',
        )

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['clinic_id'] = self.clinic.id
        session['clinic_type'] = self.clinic.clinic_type
        session['clinic_name'] = self.clinic.name
        session.save()

    def test_dentist_can_view_patient_chart_and_prescription_option(self):
        self.login(self.dentist)
        patient_response = self.client.get(reverse('core:patient_detail', args=[self.patient.patient_id]))
        self.assertEqual(patient_response.status_code, 200)
        self.assertContains(patient_response, 'Add Prescription')

        chart_response = self.client.get(reverse('DurielDentalApp:patient_chart', args=[self.patient.patient_id]))
        self.assertEqual(chart_response.status_code, 200)

    def test_dentist_cannot_create_patient_or_dental_appointment(self):
        self.login(self.dentist)
        patient_create = self.client.get(reverse('core:add_patient'))
        appointment_create = self.client.get(reverse('DurielDentalApp:appointment_create'))
        self.assertEqual(patient_create.status_code, 403)
        self.assertEqual(appointment_create.status_code, 403)

    def test_dentist_can_view_appointments_but_receptionist_cannot_open_chart(self):
        self.login(self.dentist)
        list_response = self.client.get(reverse('DurielDentalApp:appointment_list'))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, self.patient.full_name)

        self.login(self.receptionist)
        chart_response = self.client.get(reverse('DurielDentalApp:patient_chart', args=[self.patient.patient_id]))
        self.assertEqual(chart_response.status_code, 302)

    def test_new_dental_appointment_notifies_dentist(self):
        self.login(self.receptionist)
        response = self.client.post(reverse('DurielDentalApp:appointment_create'), {
            'patient': self.patient.pk,
            'provider': self.dentist.pk,
            'visit_type': 'CONSULTATION',
            'payment_type': 'SELF',
            'date': (timezone.localdate() + timedelta(days=2)).isoformat(),
            'start_time': '10:00',
            'end_time': '10:30',
            'chief_complaint': 'Sensitivity',
            'notes': '',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Notification.objects.filter(
                user=self.dentist,
                clinic=self.clinic,
                app_name='dental',
                message__icontains='New dental appointment',
            ).exists()
        )
