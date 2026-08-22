import hashlib
import hmac
import uuid
from datetime import timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.models import Clinic, CustomUser, PaymentTransaction, PendingClinicRegistration


PLAN_PRICES = {
    'MONTHLY': Decimal('15000.00'),
    'YEARLY': Decimal('150000.00'),
}
PAYSTACK_INITIALIZE_URL = 'https://api.paystack.co/transaction/initialize'
PAYSTACK_VERIFY_URL = 'https://api.paystack.co/transaction/verify/{reference}'


class PaymentError(Exception):
    pass


class PaymentInitializationError(PaymentError):
    pass


class PaymentVerificationError(PaymentError):
    pass


class PaymentPendingError(PaymentError):
    pass


def get_plan_amount(plan_type):
    try:
        return PLAN_PRICES[plan_type]
    except KeyError as exc:
        raise ValidationError('Invalid subscription plan.') from exc


def pay_amount_for_plan(plan_type):
    return int(get_plan_amount(plan_type))


def _paystack_headers():
    if not settings.PAYSTACK_SECRET_KEY:
        raise PaymentInitializationError('Paystack secret key is not configured.')
    return {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }


def build_reference():
    return f'DM-{uuid.uuid4().hex.upper()}'


def create_registration_payment(*, registration_data, plan_type, callback_url):
    amount = get_plan_amount(plan_type)
    email = registration_data['email']
    with transaction.atomic():
        payment = PaymentTransaction.objects.create(
            reference=build_reference(),
            email=email,
            plan_type=plan_type,
            amount=amount,
            currency='NGN',
        )
        safe_payload = {
            key: value
            for key, value in registration_data.items()
            if key not in {'password'}
        }
        PendingClinicRegistration.objects.create(
            payment=payment,
            clinic_name=registration_data['clinic_name'],
            clinic_type=registration_data.get('clinic_type') or 'GENERAL',
            clinic_address=registration_data.get('clinic_address', ''),
            clinic_phone=registration_data.get('clinic_phone', ''),
            clinic_email=registration_data.get('clinic_email', ''),
            title=registration_data.get('title', ''),
            first_name=registration_data.get('first_name', ''),
            last_name=registration_data.get('last_name', ''),
            phone=registration_data.get('phone', '') or registration_data.get('phone_number', ''),
            username=registration_data['username'],
            email=email,
            password_hash=make_password(registration_data['password']),
            registration_payload=safe_payload,
            expires_at=timezone.now() + timedelta(hours=24),
        )
    return initialize_paystack_transaction(payment, callback_url=callback_url)


def create_renewal_payment(*, clinic, plan_type, email, callback_url):
    amount = get_plan_amount(plan_type)
    payment = PaymentTransaction.objects.create(
        reference=build_reference(),
        clinic=clinic,
        email=email,
        plan_type=plan_type,
        amount=amount,
        currency='NGN',
    )
    return initialize_paystack_transaction(payment, callback_url=callback_url)


def initialize_paystack_transaction(payment, *, callback_url):
    payload = {
        'email': payment.email,
        'amount': int(payment.amount * 100),
        'reference': payment.reference,
        'callback_url': callback_url,
    }
    try:
        response = requests.post(
            PAYSTACK_INITIALIZE_URL,
            json=payload,
            headers=_paystack_headers(),
            timeout=20,
        )
        data = response.json()
    except requests.RequestException as exc:
        payment.provider_response = {'error': str(exc)}
        payment.save(update_fields=['provider_response', 'updated_at'])
        raise PaymentInitializationError('Payment initialization failed. Please try again.') from exc
    except ValueError as exc:
        payment.provider_response = {'error': 'Invalid Paystack response'}
        payment.save(update_fields=['provider_response', 'updated_at'])
        raise PaymentInitializationError('Payment initialization failed. Please try again.') from exc

    payment.provider_response = data
    if not data.get('status'):
        payment.status = 'FAILED'
        payment.save(update_fields=['status', 'provider_response', 'updated_at'])
        raise PaymentInitializationError(data.get('message') or 'Payment initialization failed.')

    payment.save(update_fields=['provider_response', 'updated_at'])
    try:
        authorization_url = data['data']['authorization_url']
    except (KeyError, TypeError) as exc:
        raise PaymentInitializationError('Paystack did not return a checkout URL.') from exc
    return payment, authorization_url


def confirm_paystack_payment(reference):
    if not reference:
        raise PaymentVerificationError('Payment reference not found.')

    payment = PaymentTransaction.objects.filter(reference=reference).first()
    if not payment:
        raise PaymentVerificationError('Unknown payment reference.')

    try:
        response = requests.get(
            PAYSTACK_VERIFY_URL.format(reference=reference),
            headers=_paystack_headers(),
            timeout=20,
        )
        verified = response.json()
    except requests.RequestException as exc:
        raise PaymentPendingError('Payment verification is temporarily unavailable.') from exc
    except ValueError as exc:
        raise PaymentPendingError('Payment verification returned an invalid response.') from exc

    data = verified.get('data') or {}
    if not (verified.get('status') and data.get('status') == 'success'):
        _mark_payment_failed(reference, verified)
        raise PaymentVerificationError(verified.get('message') or 'Payment verification failed.')

    if data.get('reference') != payment.reference:
        _mark_payment_failed(reference, verified)
        raise PaymentVerificationError('Payment reference mismatch.')

    expected_amount = int(payment.amount * 100)
    if int(data.get('amount') or 0) != expected_amount:
        _mark_payment_failed(reference, verified)
        raise PaymentVerificationError('Payment amount mismatch.')

    if (data.get('currency') or '').upper() != payment.currency:
        _mark_payment_failed(reference, verified)
        raise PaymentVerificationError('Payment currency mismatch.')

    with transaction.atomic():
        locked = PaymentTransaction.objects.select_for_update().get(reference=reference)
        if locked.status == 'PAID':
            return locked

        locked.status = 'PAID'
        locked.paid_at = timezone.now()
        locked.provider_response = verified
        locked.save(update_fields=['status', 'paid_at', 'provider_response', 'updated_at'])
        fulfil_payment(locked)
        return locked


def _mark_payment_failed(reference, provider_response):
    PaymentTransaction.objects.filter(reference=reference).exclude(status='PAID').update(
        status='FAILED',
        provider_response=provider_response,
        updated_at=timezone.now(),
    )


def fulfil_payment(payment):
    if payment.clinic_id:
        payment.clinic.set_subscription(payment.plan_type)
        return payment.clinic

    pending = payment.pending_registration
    if pending.completed_at:
        return CustomUser.objects.get(username=pending.username).primary_clinic
    if pending.expires_at <= timezone.now():
        raise PaymentVerificationError('Pending registration has expired.')

    valid_clinic_types = {'GENERAL', 'EYE', 'DENTAL'}
    clinic_type = pending.clinic_type if pending.clinic_type in valid_clinic_types else 'GENERAL'
    clinic = Clinic.objects.create(
        name=pending.clinic_name,
        clinic_type=clinic_type,
        address=pending.clinic_address,
        phone=pending.clinic_phone,
        email=pending.clinic_email or pending.email,
    )
    clinic.set_subscription(payment.plan_type)
    user = CustomUser.objects.create(
        username=pending.username,
        email=pending.email,
        password=pending.password_hash,
        first_name=pending.first_name,
        last_name=pending.last_name,
        is_active=True,
        role='ADMIN',
        primary_clinic=clinic,
    )
    user.title = pending.title
    user.phone = pending.phone
    user.primary_clinic = clinic
    user.save()
    user.clinic.add(clinic)
    pending.completed_at = timezone.now()
    pending.save(update_fields=['completed_at', 'updated_at'])
    payment.clinic = clinic
    payment.save(update_fields=['clinic', 'updated_at'])
    return clinic


def paystack_callback_url(request):
    return request.build_absolute_uri(reverse('core:paystack_callback'))


def valid_paystack_signature(raw_body, signature):
    if not settings.PAYSTACK_SECRET_KEY or not signature:
        return False
    digest = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(digest, signature)
