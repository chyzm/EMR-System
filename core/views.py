from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from django.utils import timezone
from datetime import date, timedelta, datetime
from decimal import Decimal
from django.db import transaction
from django.http import Http404, HttpResponse
import csv

from .models import CustomUser, Patient, Billing, Clinic, Payment, Prescription 
from .forms import CustomUserCreationForm, PatientForm, BillingForm, UserCreationWithRoleForm, UserEditForm
from DurielMedicApp.decorators import role_required
from django.http import JsonResponse
from .models import Patient
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.db.models import Sum

from django.contrib.auth.views import LoginView
from .models import Clinic
from core.decorators import clinic_selected_required
from DurielMedicApp.models import Appointment, MedicalRecord  
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.db.models import Q
from .models import ActionLog
from .utils import log_action
from django import forms
from django.urls import reverse
from DurielEyeApp.models import EyeAppointment
from .models import Notification, NotificationRead












# ---------- Role Checks ----------
def staff_check(user):
    return user.is_authenticated and user.role in ['ADMIN', 'DOCTOR', 'NURSE', 'OPTOMETRIST', 'PHYSIOTHERAPIST', 'RECEPTIONIST']

def admin_check(user):
    return user.is_authenticated and user.role == 'ADMIN'


# ---------- HOME ----------
# @login_required
# def home_view(request):
#     return redirect('DurielMedicApp:dashboard')


# Replace the existing CustomLoginView and logout_view in views.py with these fixed versions:

from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.views import LoginView
from .utils import log_login, log_logout

# views.py (snippet)
class CustomLoginView(LoginView):
    template_name = 'registration/login.html'

    def form_valid(self, form):
        response = super().form_valid(form)

        # If no clinic in session but user has primary_clinic, set it
        if not self.request.session.get('clinic_id') and self.request.user.primary_clinic:
            self.request.session['clinic_id'] = self.request.user.primary_clinic.id
            self.request.session['clinic_type'] = self.request.user.primary_clinic.clinic_type
            self.request.session['clinic_name'] = self.request.user.primary_clinic.name

            # Now that clinic exists, it's safe to log login here
            from .utils import log_login
            log_login(self.request, self.request.user)
        else:
            # No clinic yet — mark pending (handled inside log_login)
            from .utils import log_login
            log_login(self.request, self.request.user)

        return response



def logout_view(request):
    """Custom logout view with proper logging"""
    user = request.user if request.user.is_authenticated else None
    
    # ✅ Log logout BEFORE actually logging out
    if user:
        log_logout(request, user)
    
    # Now perform the actual logout
    auth_logout(request)
    return redirect('login')


def home(request):
    return render(request, 'core/login.html')




# views.py (snippet)
@login_required
def select_clinic(request):
    user_clinics = request.user.clinic.all().order_by('clinic_type', 'name')

    if request.method == 'POST':
        clinic_id = request.POST.get('clinic_id')
        clinic = Clinic.objects.filter(id=clinic_id, staff=request.user).first()
        if clinic:
            request.session['clinic_id'] = clinic.id
            request.session['clinic_type'] = clinic.clinic_type
            request.session['clinic_name'] = clinic.name

            # >>> Add these two lines <<<
            from .utils import finalize_pending_login, log_login
            finalize_pending_login(request)      # attaches pending login (if any) to this clinic
            log_login(request, request.user)     # also log an explicit login-at-clinic selection

            if clinic.clinic_type == 'GENERAL':
                return redirect('DurielMedicApp:dashboard')
            elif clinic.clinic_type == 'EYE':
                return redirect('DurielEyeApp:eye_dashboard')
            elif clinic.clinic_type == 'DENTAL':
                return redirect('DurielDentalApp:dental_dashboard')

    return render(request, 'select-clinic/select_clinic.html', {
        'clinics': user_clinics,
        'clinic_types': dict(Clinic.CLINIC_TYPES)
    })



# @login_required
# def select_clinic(request):
#     user_clinics = request.user.clinic.all().order_by('clinic_type', 'name')
    
#     if request.method == 'POST':
#         clinic_id = request.POST.get('clinic_id')
#         clinic = Clinic.objects.filter(id=clinic_id, staff=request.user).first()
#         if clinic:
#             request.session['clinic_id'] = clinic.id
#             request.session['clinic_type'] = clinic.clinic_type
#             request.session['clinic_name'] = clinic.name

#             if clinic.clinic_type == 'GENERAL':
#                 return redirect('DurielMedicApp:dashboard')
#             elif clinic.clinic_type == 'EYE':
#                 return redirect('eye_dashboard')
#             elif clinic.clinic_type == 'DENTAL':
#                 return redirect('dental_dashboard')

#     return render(request, 'select-clinic/select_clinic.html', {
#         'clinics': user_clinics,
#         'clinic_types': dict(Clinic.CLINIC_TYPES)
#            })


# ---------- USER ROLE MANAGEMENT ----------

@login_required
def manage_user_roles(request):
    # 🔹 Only superusers can see other superusers
    if request.user.is_superuser:
        users = CustomUser.objects.all()
    else:
        users = CustomUser.objects.filter(is_superuser=False)

    new_user_form = UserCreationWithRoleForm()
    new_user_form.fields['clinic'].queryset = Clinic.objects.all()
    role_forms = {user.id: UserEditForm(instance=user) for user in users}

    if request.method == 'POST':
        if 'create_user' in request.POST:
            new_user_form = UserCreationWithRoleForm(request.POST)
            if new_user_form.is_valid():
                new_user_form.save()
                return redirect('core:manage_roles')
        elif 'update_role' in request.POST:
            user_id = request.POST.get('user_id')
            user = get_object_or_404(CustomUser, id=user_id)
            role_form = UserEditForm(request.POST, instance=user)
            if role_form.is_valid():
                role_form.save()
                return redirect('core:manage_roles')

    return render(request, 'administration/manage_roles.html', {
        'users': users,
        'new_user_form': new_user_form,
        'role_forms': role_forms,
    })



# @login_required
# def manage_user_roles(request):
#     users = CustomUser.objects.all()
#     new_user_form = UserCreationWithRoleForm()
#     new_user_form.fields['clinic'].queryset = Clinic.objects.all()
#     role_forms = {user.id: UserEditForm(instance=user) for user in users}

#     if request.method == 'POST':
#         if 'create_user' in request.POST:
#             new_user_form = UserCreationWithRoleForm(request.POST)
#             if new_user_form.is_valid():
#                 new_user_form.save()
#                 return redirect('core:manage_roles')
#         elif 'update_role' in request.POST:
#             user_id = request.POST.get('user_id')
#             user = get_object_or_404(CustomUser, id=user_id)
#             role_form = UserEditForm(request.POST, instance=user)
#             if role_form.is_valid():
#                 role_form.save()
#                 return redirect('core:manage_roles')

#     return render(request, 'administration/manage_roles.html', {
#         'users': users,
#         'new_user_form': new_user_form,
#         'role_forms': role_forms,
#     })


@login_required
def edit_user_role(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    editing_self = (request.user.id == user.id)
    
    if request.method == 'POST':
        form = UserEditForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            # Prevent non-superusers from making superusers
            if not request.user.is_superuser and form.cleaned_data.get('is_superuser'):
                messages.error(request, "Only superusers can create other superusers.")
                return redirect('core:manage_roles')
            
            # Prevent users from deactivating themselves
            if editing_self and not form.cleaned_data.get('is_active'):
                messages.error(request, "You cannot deactivate yourself.")
                return redirect('core:manage_roles')
                
            form.save()

            # ✅ Manual logging
            from .utils import log_action
            log_action(
                request,
                'UPDATE',
                user,
                details=f"Updated user role/details for {user.get_full_name() or user.username}"
            )

            messages.success(request, 'User details updated successfully.')
            return redirect('core:manage_roles')
    else:
        form = UserEditForm(instance=user)
        form.fields['clinic'].queryset = Clinic.objects.all()
        
        # Hide superuser checkbox for non-superusers
        if not request.user.is_superuser:
            form.fields['is_superuser'].widget = forms.HiddenInput()

    return render(request, 'dashboard/edit_user_role.html', {
        'form': form,
        'user_obj': user,
        'editing_self': editing_self,
    })



# ---------- PATIENTS ----------



class PatientListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Patient
    template_name = 'patients/patient_list.html'
    context_object_name = 'patients'
    paginate_by = 10

    def test_func(self):
        return self.request.user.role in ['ADMIN', 'DOCTOR', 'NURSE', 'RECEPTIONIST']

    def get_queryset(self):
        clinic_id = self.request.session.get('clinic_id')
        queryset = super().get_queryset()

        if clinic_id:
            queryset = queryset.filter(clinic_id=clinic_id)

        search_name = self.request.GET.get('search', '')
        search_id = self.request.GET.get('patient_id', '')

        if search_name:
            queryset = queryset.filter(full_name__icontains=search_name)
        if search_id:
            queryset = queryset.filter(patient_id__icontains=search_id)

        return queryset.order_by('-created_at')


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('search', '')
        return context
    
    

class PatientCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Patient
    form_class = PatientForm
    template_name = 'patients/add_patient.html'
    success_url = reverse_lazy('core:patient_list')

    def test_func(self):
        return self.request.user.role in ['ADMIN', 'DOCTOR', 'RECEPTIONIST', 'NURSE', 'OPTOMETRIST']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        # Ensure clinic is set before saving
        if not form.instance.clinic_id:
            clinic_id = self.request.session.get('clinic_id')
            if not clinic_id:
                messages.error(self.request, "No clinic selected. Please select a clinic first.")
                return redirect('core:select_clinic')
            form.instance.clinic_id = clinic_id
        
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Patient added successfully!')
        return super().form_valid(form)
    # ✅ Manual logging
        from .utils import log_action
        log_action(
                request,
                'UPDATE',
                user,
                details=f"Updated user role/details for {user.get_full_name() or user.username}"
            )

# class PatientUpdateView(UpdateView):
#     model = Patient
#     fields = ['full_name', 'date_of_birth', 'gender', 'contact', 'address']
#     template_name = 'patients/edit_patient.html'
#     success_url = reverse_lazy('core:patient_list')

class PatientUpdateView(UpdateView):
    model = Patient
    form_class = PatientForm
    template_name = 'patients/edit_patient.html'
    success_url = reverse_lazy('core:patient_list')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        
        # ✅ Manual logging
        log_action(
            self.request,
            'UPDATE',
            form.instance,
            details=f"Updated patient: {form.instance.full_name}"
        )
        
        return response



# class PatientDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
#     model = Patient
#     template_name = 'patients/patient_detail.html'
#     context_object_name = 'patient'
    
#     def test_func(self):
#         return self.request.user.is_authenticated and self.request.user.role in ['ADMIN', 'DOCTOR', 'NURSE', 'RECEPTIONIST', 'OPTOMETRIST']
    
    
#     def get_object(self, queryset=None):
#         clinic_id = self.request.session.get('clinic_id')
#         patient = super().get_object(queryset)
        
#         if clinic_id and patient.clinic_id != clinic_id:
#             raise Http404("Patient not found.")
#         return patient
    
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         patient = self.get_object()
        
#         # Get the latest vitals if available (from general appointments)
#         appointment = patient.appointments.filter(status='SCHEDULED').first()
#         if appointment:
#             context['vitals'] = getattr(appointment, 'vitals', None)
        
#         # Add all required context data
#         context['medical_records'] = MedicalRecord.objects.filter(patient=patient).order_by('-created_at')
        
#         # Regular appointments from DurielMedicApp
#         context['appointments'] = Appointment.objects.filter(patient=patient).order_by('-date', '-start_time')
        
#         # Eye appointments from DurielEyeApp - need to import EyeAppointment at top
#         from DurielEyeApp.models import EyeAppointment
#         context['eye_appointments'] = EyeAppointment.objects.filter(patient=patient).order_by('-date', '-start_time')
        
#         context['prescriptions'] = Prescription.objects.filter(patient=patient, is_active=True).order_by('-date_prescribed')
#         context['deactivated_prescriptions'] = Prescription.objects.filter(patient=patient, is_active=False).order_by('-date_prescribed')
#         context['bills'] = Billing.objects.filter(patient=patient).order_by('-service_date')
    
        
#         return context

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

class PatientDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Patient
    template_name = 'patients/patient_detail.html'
    context_object_name = 'patient'
    
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role in ['ADMIN', 'DOCTOR', 'NURSE', 'RECEPTIONIST', 'OPTOMETRIST']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        patient = self.get_object()

        # Define items per page once and reuse everywhere
        items_per_page = 1

        # Get the latest vitals if available (from general appointments)
        appointment = patient.appointments.filter(status='SCHEDULED').first()
        if appointment:
            context['vitals'] = getattr(appointment, 'vitals', None)

        # Medical Records Pagination (show for both GENERAL and EYE clinics)
        medical_records_list = MedicalRecord.objects.filter(patient=patient).order_by('-created_at')
        medical_paginator = Paginator(medical_records_list, items_per_page)
        medical_page = self.request.GET.get('medical_page', 1)
        
        try:
            medical_records = medical_paginator.page(medical_page)
        except PageNotAnInteger:
            medical_records = medical_paginator.page(1)
        except EmptyPage:
            medical_records = medical_paginator.page(medical_paginator.num_pages)
        
        context['medical_records'] = medical_records

        # Eye Medical Records Pagination (for EYE clinic)
        if self.request.session.get('clinic_type') == 'EYE':
            eye_medical_records_list = patient.eye_medical_records.all().order_by('-created_at')
            eye_medical_paginator = Paginator(eye_medical_records_list, items_per_page)
            eye_medical_page = self.request.GET.get('eye_medical_page', 1)
            try:
                eye_medical_records = eye_medical_paginator.page(eye_medical_page)
            except PageNotAnInteger:
                eye_medical_records = eye_medical_paginator.page(1)
            except EmptyPage:
                eye_medical_records = eye_medical_paginator.page(eye_medical_paginator.num_pages)
            context['eye_medical_records'] = eye_medical_records

        # Eye Exams Pagination (only for EYE clinic)
        if self.request.session.get('clinic_type') == 'EYE':
            eye_exams_list = patient.eye_exams.all().order_by('-created_at')
            exams_paginator = Paginator(eye_exams_list, items_per_page)
            exams_page = self.request.GET.get('exams_page', 1)
            try:
                eye_exams = exams_paginator.page(exams_page)
            except PageNotAnInteger:
                eye_exams = exams_paginator.page(1)
            except EmptyPage:
                eye_exams = exams_paginator.page(exams_paginator.num_pages)
            context['eye_exams'] = eye_exams

        # Appointments Pagination (Regular) - Most recent first
        appointments_list = Appointment.objects.filter(patient=patient).order_by('-date', '-start_time')
        appointments_paginator = Paginator(appointments_list, items_per_page)
        appointments_page = self.request.GET.get('appointments_page', 1)
        try:
            appointments = appointments_paginator.page(appointments_page)
        except PageNotAnInteger:
            appointments = appointments_paginator.page(1)
        except EmptyPage:
            appointments = appointments_paginator.page(appointments_paginator.num_pages)
        context['appointments'] = appointments

        # Eye Appointments Pagination - Most recent first
        eye_appointments_list = EyeAppointment.objects.filter(patient=patient).order_by('-date', '-start_time')
        eye_appointments_paginator = Paginator(eye_appointments_list, items_per_page)
        eye_appointments_page = self.request.GET.get('eye_appointments_page', 1)
        try:
            eye_appointments = eye_appointments_paginator.page(eye_appointments_page)
        except PageNotAnInteger:
            eye_appointments = eye_appointments_paginator.page(1)
        except EmptyPage:
            eye_appointments = eye_appointments_paginator.page(eye_appointments_paginator.num_pages)
        context['eye_appointments'] = eye_appointments

        # Prescriptions Pagination (Active) - Most recent first
        prescriptions_list = Prescription.objects.filter(patient=patient, is_active=True).order_by('-date_prescribed')
        prescriptions_paginator = Paginator(prescriptions_list, items_per_page)
        prescriptions_page = self.request.GET.get('prescriptions_page', 1)
        try:
            prescriptions = prescriptions_paginator.page(prescriptions_page)
        except PageNotAnInteger:
            prescriptions = prescriptions_paginator.page(1)
        except EmptyPage:
            prescriptions = prescriptions_paginator.page(prescriptions_paginator.num_pages)
        context['prescriptions'] = prescriptions

        # Deactivated Prescriptions Pagination - Most recent first
        deactivated_prescriptions_list = Prescription.objects.filter(patient=patient, is_active=False).order_by('-date_prescribed')
        deactivated_prescriptions_paginator = Paginator(deactivated_prescriptions_list, items_per_page)
        deactivated_prescriptions_page = self.request.GET.get('deactivated_prescriptions_page', 1)
        try:
            deactivated_prescriptions = deactivated_prescriptions_paginator.page(deactivated_prescriptions_page)
        except PageNotAnInteger:
            deactivated_prescriptions = deactivated_prescriptions_paginator.page(1)
        except EmptyPage:
            deactivated_prescriptions = deactivated_prescriptions_paginator.page(deactivated_prescriptions_paginator.num_pages)
        context['deactivated_prescriptions'] = deactivated_prescriptions

        # Bills Pagination - Most recent first
        bills_list = Billing.objects.filter(patient=patient).order_by('-service_date')
        bills_paginator = Paginator(bills_list, items_per_page)
        bills_page = self.request.GET.get('bills_page', 1)
        try:
            bills = bills_paginator.page(bills_page)
        except PageNotAnInteger:
            bills = bills_paginator.page(1)
        except EmptyPage:
            bills = bills_paginator.page(bills_paginator.num_pages)
        context['bills'] = bills

        return context





class PatientDeleteView(DeleteView):
    model = Patient
    template_name = 'patients/confirm_delete.html'
    success_url = reverse_lazy('core:patient_list')
    
    def delete(self, request, *args, **kwargs):
        patient = self.get_object()
        
        # ✅ Manual logging
        log_action(
            request,
            'DELETE',
            patient,
            details=f"Deleted patient: {patient.full_name}"
        )
        
        messages.success(request, f"Patient {patient.full_name} deleted successfully.")
        return super().delete(request, *args, **kwargs)


# ---------- STAFF ----------
@login_required
@user_passes_test(admin_check)
def staff_list(request):
    staff = CustomUser.objects.filter(is_staff=True).exclude(role='ADMIN').order_by('last_name', 'first_name')
    return render(request, 'staff/staff_list.html', {'staff': staff})


class StaffCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = CustomUser
    form_class = UserCreationWithRoleForm
    template_name = 'dashboard/add_user.html'
    success_url = reverse_lazy('core:admin_dashboard')

    def test_func(self):
        return self.request.user.is_superuser or (
            self.request.user.role == 'ADMIN' and self.request.user.is_staff
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request  # safely pass request
        kwargs.setdefault('initial', {}).update({
            'is_active': True,
            'is_staff': True,
        })
        return kwargs

    def form_valid(self, form):
        user = form.save(commit=False)
        user.is_staff = True
        user.save()
        form.save_m2m()
        messages.success(self.request, f'User {user.username} created successfully!')
        return super().form_valid(form)






# ---------- Billing ----------


@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def billing_list(request):
    clinic_id = request.session.get('clinic_id')
    if not clinic_id:
        messages.error(request, "No clinic selected. Please select a clinic first.")
        return redirect('core:select_clinic')

    bills = Billing.objects.filter(clinic_id=clinic_id).select_related('patient').order_by('-service_date')
    
    # Filtering options
    status_filter = request.GET.get('status', '')
    if status_filter:
        bills = bills.filter(status=status_filter)
    
    patient_filter = request.GET.get('patient', '')
    if patient_filter:
        bills = bills.filter(patient__full_name__icontains=patient_filter)
    
    date_from = request.GET.get('date_from', '')
    if date_from:
        bills = bills.filter(service_date__gte=date_from)
    
    date_to = request.GET.get('date_to', '')
    if date_to:
        bills = bills.filter(service_date__lte=date_to)
    
    context = {
        'bills': bills,
        'total_amount': bills.aggregate(total=Sum('amount'))['total'] or 0,
        'total_paid': bills.aggregate(total=Sum('paid_amount'))['total'] or 0,
        'status_filter': status_filter,
        'patient_filter': patient_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'billing/billing_list.html', context)



@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def create_bill(request, patient_id=None):
    clinic_id = request.session.get('clinic_id')
    if not clinic_id:
        messages.error(request, "No clinic selected.")
        return redirect('select_clinic')

    # Only show patients from the current clinic
    patients_with_appointments = Patient.objects.filter(clinic_id=clinic_id)

    # Get selected patient from GET parameters
    selected_patient_id = request.GET.get('patient')
    patient = None
    if selected_patient_id:
        try:
            patient = Patient.objects.get(patient_id=selected_patient_id, clinic_id=clinic_id)  # Filter by clinic
        except Patient.DoesNotExist:
            pass
    elif patient_id:
        try:
            patient = Patient.objects.get(pk=patient_id, clinic_id=clinic_id)  # Filter by clinic
        except Patient.DoesNotExist:
            patient = None

    if request.method == 'POST':
        form = BillingForm(request.POST)
        if form.is_valid():
            bill = form.save(commit=False)
            bill.created_by = request.user
            bill.clinic = get_object_or_404(Clinic, id=clinic_id)
            if not bill.paid_amount:
                bill.paid_amount = 0
            if bill.paid_amount == bill.amount:
                bill.status = 'PAID'
            elif bill.paid_amount > 0:
                bill.status = 'PARTIAL'
            else:
                bill.status = 'PENDING'
            bill.save()
            
            # ✅ Manual logging
            log_action(
                request,
                'CREATE',
                bill,
                details=f"Created bill #{bill.id} for {bill.patient.full_name} - Amount: {bill.amount}"
            )
        
        
            messages.success(request, "Bill created successfully!")
            return redirect('core:billing_list')
    else:
        form = BillingForm(initial={'service_date': date.today()})
        if patient:
            form.initial['patient'] = patient.patient_id

    # Get appointment
    appointment_id = request.GET.get('appointment_id')
    if appointment_id:
        appointment = Appointment.objects.filter(id=appointment_id, clinic_id=clinic_id).first()
    elif patient:
        appointment = Appointment.objects.filter(patient=patient, clinic_id=clinic_id).order_by('-date', '-start_time').first()
    else:
        appointment = None

    return render(request, 'billing/billing_form.html', {
        'form': form,
        'patient': patient,
        'patients_with_appointments': patients_with_appointments,
        'appointment': appointment,
        'selected_patient_id': selected_patient_id,
    })




@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def edit_bill(request, pk):
    bill = get_object_or_404(Billing, pk=pk)
    patients_with_appointments = Patient.objects.filter(
        appointments__isnull=False
    ).distinct()
    
    if request.method == 'POST':
        form = BillingForm(request.POST, instance=bill)
        if form.is_valid():
            updated_bill = form.save(commit=False)
            
            if updated_bill.paid_amount > updated_bill.amount:
                messages.error(request, "Paid amount cannot be greater than total amount")
                return render(request, 'billing/billing_form.html', {
                    'form': form, 
                    'bill': bill,
                    'patients_with_appointments': patients_with_appointments
                })
            
            if updated_bill.paid_amount == updated_bill.amount:
                updated_bill.status = 'PAID'
            elif updated_bill.paid_amount > 0:
                updated_bill.status = 'PARTIAL'
            else:
                updated_bill.status = 'PENDING'
            
            updated_bill.save()
            
            # ✅ Manual logging
            log_action(
                request,
                'UPDATE',
                updated_bill,
                details=f"Updated bill #{updated_bill.id} for {updated_bill.patient.full_name}"
            )
            
            messages.success(request, "Bill updated successfully!")
            return redirect('core:view_bill', pk=bill.pk)
    else:
        form = BillingForm(instance=bill)
        
    

    
    return render(request, 'billing/billing_form.html', {
        'form': form,
        'bill': bill,
        'patients_with_appointments': patients_with_appointments,
        'title': 'Edit Bill'
    })
    
    


@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def record_payment(request, pk):
    bill = get_object_or_404(Billing, pk=pk)
    
    if request.method == 'POST':
        payment_amount = Decimal(request.POST.get('payment_amount', '0'))
        
        if payment_amount <= 0:
            messages.error(request, "Payment amount must be greater than zero")
            return redirect('core:view_bill', pk=bill.pk)
        
        if payment_amount > (bill.amount - bill.paid_amount):
            messages.error(request, "Payment amount exceeds outstanding balance")
            return redirect('core:view_bill', pk=bill.pk)
        
        with transaction.atomic():
            bill.paid_amount += payment_amount
            
            if bill.paid_amount == bill.amount:
                bill.status = 'PAID'
            else:
                bill.status = 'PARTIAL'
            
            bill.save()
            
            # ✅ Manual logging
            log_action(
                request,
                'UPDATE',
                bill,
                details=f"Recorded payment of ₦{payment_amount:,.2f} for {bill.patient.full_name}"
            )
            
            # Create payment record
            Payment.objects.create(
                billing=bill,
                amount=payment_amount,
                received_by=request.user,
                payment_method=request.POST.get('payment_method', 'CASH')
            )
            
            messages.success(request, f"Payment of ₦{payment_amount:,.2f} recorded successfully!")
        
        return redirect('core:view_bill', pk=bill.pk)
    
    return render(request, 'billing/record_payment.html', {'bill': bill})


@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST', 'DOCTOR', 'NURSE')
def view_bill(request, pk):
    bill = get_object_or_404(Billing, pk=pk)
    return render(request, 'billing/bill_detail.html', {'bill': bill})


@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def delete_bill(request, pk):
    bill = get_object_or_404(Billing, pk=pk)
    if request.method == 'POST':
        
        # ✅ Manual logging
        log_action(
            request,
            'DELETE',
            bill,
            details=f"Deleted bill #{bill.id} for {bill.patient.full_name}"
        )
        bill.delete()
        messages.success(request, "Bill deleted successfully!")
        return redirect('core:billing_list')
    return render(request, 'billing/confirm_delete.html', {'bill': bill})



# def logout_view(request):
#     logout(request)
#     return redirect('login')  # or 'core:login' if namespaced





def patient_search_api(request):
    query = request.GET.get('q', '')
    results = Patient.objects.filter(full_name__icontains=query)
    data = [{'id': p.id, 'name': p.full_name} for p in results]
    return JsonResponse({'results': data})






@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def generate_receipt(request, pk):
    bill = get_object_or_404(Billing, pk=pk)
    payments = bill.payments.all().order_by('-payment_date')

    if payments.exists():
        payment = payments.first()  # latest payment
    else:
        payment = None

    context = {
        'bill': bill,
        'payment': payment,
        'payments': payments,
        'outstanding': bill.amount - bill.paid_amount,
        'today': timezone.now().date()
    }

    return render(request, 'billing/receipt.html', context)


import os
import json
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv

load_dotenv()  # Load environment variables

AI_API_KEY = os.getenv("OPENROUTER_API_KEY")

@csrf_exempt
def ai_chat(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            prompt = data.get("prompt", "")

            if not AI_API_KEY:
                return JsonResponse({"answer": "Error: API key not set"}, status=500)

            res = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {AI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "You are a helpful medical assistant for doctors."},
                        {"role": "user", "content": prompt}
                    ]
                }
            )

            if res.status_code != 200:
                return JsonResponse({"answer": f"API Error: {res.text}"}, status=500)

            answer = res.json()["choices"][0]["message"]["content"]
            return JsonResponse({"answer": answer})

        except Exception as e:
            return JsonResponse({"answer": f"Server error: {e}"}, status=500)

    return JsonResponse({"error": "Invalid request"}, status=400)


# Admin Dashboard and Management 

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Count, Sum
from .models import Patient, Clinic, CustomUser, Billing
from DurielMedicApp.models import Appointment
from .forms import ClinicForm

from django.core.paginator import Paginator
from django.db.models import Q

@login_required
@user_passes_test(lambda u: u.is_superuser or u.role == 'ADMIN')
def admin_dashboard(request):
    # Clinics Management with search and pagination
    clinic_search = request.GET.get('clinic_search', '')
    clinic_page = request.GET.get('clinic_page', 1)
    
    clinics = Clinic.objects.all().order_by('name')  # Added ordering by name
    if clinic_search:
        clinics = clinics.filter(
            Q(name__icontains=clinic_search) | 
            Q(clinic_type__icontains=clinic_search) |
            Q(address__icontains=clinic_search)
        )
    
    clinic_paginator = Paginator(clinics, 10)  # Show 10 clinics per page
    try:
        clinic_page_obj = clinic_paginator.page(clinic_page)
    except PageNotAnInteger:
        clinic_page_obj = clinic_paginator.page(1)
    except EmptyPage:
        clinic_page_obj = clinic_paginator.page(clinic_paginator.num_pages)
    
    stats = []
    for clinic in clinic_page_obj:
        clinic_stats = {
            'clinic': clinic,
            'patients': Patient.objects.filter(clinic=clinic).count(),
            'appointments': Appointment.objects.filter(clinic=clinic).count(),
            'staff': CustomUser.objects.filter(clinic=clinic).count(),
            'bills': Billing.objects.filter(clinic=clinic).aggregate(total=Sum('amount'))['total'] or 0,
            'prescriptions': Prescription.objects.filter(patient__clinic=clinic).count(),
        }
        stats.append(clinic_stats)
    
    # User Management with search and pagination
    user_search = request.GET.get('user_search', '')
    user_page = request.GET.get('user_page', 1)
    
    users = CustomUser.objects.all().order_by('last_name', 'first_name')  # Added ordering by last_name then first_name
    if user_search:
        users = users.filter(
            Q(username__icontains=user_search) |
            Q(first_name__icontains=user_search) |
            Q(last_name__icontains=user_search) |
            Q(email__icontains=user_search) |
            Q(role__icontains=user_search)
        )
    
    user_paginator = Paginator(users, 10)  # Show 10 users per page
    try:
        user_page_obj = user_paginator.page(user_page)
    except PageNotAnInteger:
        user_page_obj = user_paginator.page(1)
    except EmptyPage:
        user_page_obj = user_paginator.page(user_paginator.num_pages)
    
    context = {
        'stats': stats,
        'users': user_page_obj,
        'clinics': clinic_page_obj,
    }
    return render(request, 'dashboard/admin_dashboard.html', context)




@login_required
@user_passes_test(lambda u: u.is_superuser or u.role == 'ADMIN')
def activate_user(request, user_id):
    user = get_object_or_404(CustomUser, pk=user_id)
    user.is_active = True
    user.save()
    messages.success(request, f"{user.username} activated.")
    return redirect('admin_dashboard')

@login_required
@user_passes_test(lambda u: u.is_superuser or u.role == 'ADMIN')
def set_staff(request, user_id):
    user = get_object_or_404(CustomUser, pk=user_id)
    user.is_staff = True
    user.save()
    messages.success(request, f"{user.username} set as staff.")
    return redirect('admin_dashboard')

@login_required
@user_passes_test(lambda u: u.is_superuser or u.role == 'ADMIN')
def set_superuser(request, user_id):
    user = get_object_or_404(CustomUser, pk=user_id)
    user.is_superuser = True
    user.save()
    messages.success(request, f"{user.username} set as superuser.")
    return redirect('admin_dashboard')

@login_required
@user_passes_test(lambda u: u.is_superuser or u.role == 'ADMIN')
def verify_user(request, user_id):
    user = get_object_or_404(CustomUser, pk=user_id)
    user.verified = True  # Add this field to your CustomUser model
    user.save()
    messages.success(request, f"{user.username} verified.")
    return redirect('core:admin_dashboard')




@login_required
@user_passes_test(lambda u: u.is_superuser or u.role == 'ADMIN')
def add_clinic(request):
    if request.method == 'POST':
        form = ClinicForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Clinic added.")
            return redirect('core:admin_dashboard')
    else:
        form = ClinicForm()
    return render(request, 'dashboard/add_clinic.html', {'form': form})


@login_required
@user_passes_test(lambda u: u.is_superuser)  # or u.role == 'ADMIN'
def delete_clinic(request, pk):
    clinic = get_object_or_404(Clinic, pk=pk)
    
    if request.method == 'POST':
        try:
            clinic_name = clinic.name
            clinic.delete()
            
            # Log the action
            log_action(
                request,
                'DELETE',
                clinic,
                details=f"Deleted clinic: {clinic_name}"
            )
            
            messages.success(request, f"Clinic '{clinic_name}' has been deleted.")
            return redirect('core:admin_dashboard')
        except Exception as e:
            messages.error(request, f"Error deleting clinic: {str(e)}")
            return redirect('core:admin_dashboard')
    
    # If not POST, show confirmation page
    return render(request, 'dashboard/confirm_clinic_delete.html', {'clinic': clinic})



from django.views.generic.edit import UpdateView
from .models import Clinic
from .forms import ClinicForm

class ClinicUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Clinic
    form_class = ClinicForm
    template_name = 'dashboard/edit_clinic.html'
    success_url = '/dashboard/'

    def test_func(self):
        return self.request.user.is_superuser or self.request.user.role == 'ADMIN'
    
    

@login_required
@user_passes_test(lambda u: u.is_superuser or u.role == 'ADMIN')
def activate_user(request, user_id):
    user = get_object_or_404(CustomUser, pk=user_id)
    user.is_active = not user.is_active
    user.save()
    messages.success(request, f"{user.username} has been {'activated' if user.is_active else 'deactivated'}.")
    return redirect('core:admin_dashboard')

@login_required
@user_passes_test(lambda u: u.is_superuser or u.role == 'ADMIN')
def set_staff(request, user_id):
    user = get_object_or_404(CustomUser, pk=user_id)
    user.is_staff = not user.is_staff
    user.save()
    messages.success(request, f"{user.username} has been {'granted staff privileges' if user.is_staff else 'removed from staff'}.")
    return redirect('core:admin_dashboard')

@login_required
@user_passes_test(lambda u: u.is_superuser or u.role == 'ADMIN')
def verify_user(request, user_id):
    user = get_object_or_404(CustomUser, pk=user_id)
    user.verified = not user.verified
    user.save()
    messages.success(request, f"{user.username} has been {'verified' if user.verified else 'unverified'}.")
    return redirect('core:admin_dashboard')


@login_required
@user_passes_test(lambda u: u.is_superuser)
def toggle_superuser(request, user_id):
    if request.user.id == user_id:
        messages.error(request, "You cannot change your own superuser status.")
        return redirect('core:admin_dashboard')
    
    user = get_object_or_404(CustomUser, pk=user_id)
    user.is_superuser = not user.is_superuser
    user.save()
    status = "granted superuser privileges" if user.is_superuser else "removed from superusers"
    messages.success(request, f"{user.username} has been {status}.")
    return redirect('core:admin_dashboard')

@login_required
@user_passes_test(lambda u: u.is_superuser or u.role == 'ADMIN')
def toggle_staff(request, user_id):
    if request.user.id == user_id and not request.user.is_superuser:
        messages.error(request, "You cannot change your own staff status.")
        return redirect('core:admin_dashboard')
    
    user = get_object_or_404(CustomUser, pk=user_id)
    user.is_staff = not user.is_staff
    user.save()
    status = "added to staff" if user.is_staff else "removed from staff"
    messages.success(request, f"{user.username} has been {status}.")
    return redirect('core:admin_dashboard')

@login_required
@user_passes_test(lambda u: u.is_superuser or u.role == 'ADMIN')
def toggle_verify(request, user_id):
    user = get_object_or_404(CustomUser, pk=user_id)
    user.verified = not user.verified
    user.save()
    status = "verified" if user.verified else "unverified"
    messages.success(request, f"{user.username} has been {status}.")
    return redirect('core:admin_dashboard')
    
    
    
    
    
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Clinic
from .forms import ClinicLogoForm

@login_required
def settings_view(request):
    clinic = None
    if request.session.get('clinic_id'):
        try:
            clinic = Clinic.objects.get(id=request.session['clinic_id'])
        except Clinic.DoesNotExist:
            messages.error(request, "No clinic selected or clinic not found")
            return redirect('some_other_view')
    
    if request.method == 'POST':
        form = ClinicLogoForm(request.POST, request.FILES, instance=clinic)
        if form.is_valid():
            form.save()
            if clinic and clinic.logo:  # Check if logo exists after save
                request.session['clinic_logo'] = clinic.logo.url
            messages.success(request, "Settings updated successfully")
            return redirect('core:settings')
    else:
        form = ClinicLogoForm(instance=clinic)
    
    return render(request, 'settings/settings.html', {
        'form': form,
        'clinic': clinic,
    })
    
    
    


@login_required
@user_passes_test(lambda u: u.role == 'ADMIN')
def activity_log(request):
    clinic_id = request.session.get('clinic_id')
    if not clinic_id:
        messages.error(request, "No clinic selected")
        return redirect('core:select_clinic')
    
    try:
        clinic = Clinic.objects.get(id=clinic_id)
    except Clinic.DoesNotExist:
        messages.error(request, "Invalid clinic selected")
        return redirect('core:select_clinic')
    
    logs = ActionLog.objects.filter(clinic_id=clinic_id).select_related(
        'user', 'content_type', 'clinic'
    ).order_by('-timestamp')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        logs = logs.filter(
            Q(user__username__icontains=search_query) |
            Q(action__icontains=search_query) |
            Q(details__icontains=search_query) |
            Q(content_type__model__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(logs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'logs': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'clinic_name': clinic.name,
        'search_query': search_query
    }
    
    return render(request, 'activity-log/activity_log.html', context)




@require_POST
@login_required
@user_passes_test(lambda u: u.role == 'ADMIN')
def clear_activity_log(request):
    clinic_id = request.session.get('clinic_id')
    if not clinic_id:
        return JsonResponse({'success': False, 'error': 'No clinic selected'}, status=400)
    
    ActionLog.objects.filter(clinic_id=clinic_id).delete()
    return JsonResponse({'success': True})




import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import ActionLog

@require_POST
@login_required
@user_passes_test(lambda u: u.role == 'ADMIN')
def bulk_delete_logs(request):
    try:
        data = json.loads(request.body)  # Parse JSON from fetch request
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    
    log_ids = data.get('log_ids', [])
    if not log_ids:
        return JsonResponse({'success': False, 'error': 'No logs selected'}, status=400)
    
    deleted_count, _ = ActionLog.objects.filter(
        id__in=log_ids,
        clinic_id=request.session.get('clinic_id')
    ).delete()
    
    return JsonResponse({'success': True, 'count': deleted_count})




@login_required
def add_prescription(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id)

    if request.method == 'POST':
        medication = request.POST.get('medication')
        dosage = request.POST.get('dosage')
        instructions = request.POST.get('instructions')
        # frequency = request.POST.get('frequency')
        # duration = request.POST.get('duration')
        

        # Validation (optional)
        if not medication or not dosage:
            messages.error(request, "Please fill in all required fields.")
        else:
            prescription = Prescription.objects.create(
                patient=patient,
                medication=medication,
                dosage=dosage,
                clinic=patient.clinic,
                # frequency=frequency,
                # duration=duration,
                instructions=instructions,
                prescribed_by=request.user
            )

            
            # ✅ Manual logging
            log_action(
                request,
                'CREATE',
                prescription,
                details=f"Added prescription for {patient.full_name}"
            )
            
            
            Notification.objects.create(
                user=prescription.patient.created_by,
                message=f"New prescription for {prescription.patient.full_name}",
                link=reverse('core:patient_detail', kwargs={'pk': prescription.patient.pk})
            )
            messages.success(request, "Prescription saved successfully.")
            return redirect('core:patient_detail', pk=patient.patient_id)

    return render(request, 'prescription/add_prescription.html', {'patient': patient})



@login_required
def edit_prescription(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk)
    patient = prescription.patient

    if request.method == 'POST':
        prescription.medication = request.POST.get('medication')
        prescription.dosage = request.POST.get('dosage')
        prescription.instructions = request.POST.get('instructions')
        prescription.save()
        return redirect('core:patient_detail', pk=patient.patient_id)

    return render(request, 'prescription/edit_prescription.html', {'prescription': prescription, 'patient': patient})

@login_required
def prescription_list(request):
    clinic_id = request.session.get('clinic_id')
    if not clinic_id:
        messages.error(request, "No clinic selected. Please select a clinic first.")
        return redirect('core:select_clinic')

    query = request.GET.get('q', '')
    prescriptions = Prescription.objects.filter(patient__clinic_id=clinic_id).select_related('patient', 'prescribed_by')

    if query:
        prescriptions = prescriptions.filter(
            Q(patient__full_name__icontains=query) |
            Q(prescribed_by__first_name__icontains=query) |
            Q(prescribed_by__last_name__icontains=query) |
            Q(medication__icontains=query) |
            Q(date_prescribed__icontains=query)
        )

    context = {
        'prescriptions': prescriptions.order_by('-date_prescribed'),
        'query': query,
    }
    return render(request, 'prescription/prescription_list.html', context)



from django import shortcuts
from django.utils import timezone

@login_required
@user_passes_test(lambda u: u.role in ['ADMIN', 'DOCTOR', 'OPERATOR'])  
def deactivate_prescription(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk)
    patient = prescription.patient

    if request.method == 'POST':
        prescription.is_active = False
        prescription.deactivated_at = timezone.now()  # Add this line
        prescription.save()
        
        # ✅ Manual logging
        log_action(
            request,
            'UPDATE',
            prescription,
            details=f"Deactivated prescription for {patient.full_name}"
        )
        
        messages.success(request, "Prescription has been deactivated.")
        return redirect('core:patient_detail', pk=patient.patient_id)

    return render(request, 'prescription/deactivate_prescription.html', {
        'prescription': prescription,
        'patient': patient
    })
    
    

@login_required
@user_passes_test(lambda u: u.role in ['ADMIN', 'DOCTOR'])  # adjust roles as needed
def delete_prescription(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk, clinic_id=request.session.get('clinic_id'))
    patient = prescription.patient

    if request.method == "POST":
        # ✅ Manual logging
        log_action(
            request,
            'DELETE',
            prescription,
            details=f"Deleted prescription for {patient.full_name}"
        )
        
        prescription.delete()
        messages.success(request, "Prescription deleted successfully.")
        return redirect('core:prescription_list')

    return render(request, 'prescription/confirm_delete.html', {'prescription': prescription})






@login_required
def mark_notification_read(request, pk):
    clinic_id = request.session.get('clinic_id')
    notification = get_object_or_404(Notification, pk=pk, clinic_id=clinic_id)
    
    if notification.user == request.user:
        notification.is_read = True
        notification.save()
    elif notification.user is None:
        NotificationRead.objects.get_or_create(
            user=request.user,
            notification=notification
        )
    
    return redirect(request.META.get('HTTP_REFERER', 'core:dashboard'))

@login_required
def clear_notifications(request):
    clinic_id = request.session.get('clinic_id')
    if not clinic_id:
        messages.error(request, "No clinic selected")
        return redirect('core:select_clinic')
    
    # Delete user-specific notifications for this clinic
    request.user.notifications.filter(clinic_id=clinic_id).delete()

    # Mark global clinic notifications as read
    unread_globals = Notification.objects.filter(
        user__isnull=True,
        clinic_id=clinic_id
    ).exclude(
        id__in=NotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
    )
    NotificationRead.objects.bulk_create([
        NotificationRead(user=request.user, notification=n) for n in unread_globals
    ], ignore_conflicts=True)

    messages.success(request, "Notifications cleared")
    return redirect(request.META.get('HTTP_REFERER', 'core:dashboard'))
