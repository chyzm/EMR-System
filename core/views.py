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

from .models import CustomUser, Patient, Billing, Clinic, Payment, Prescription, ServicePriceList 
from .forms import (CustomUserCreationForm, FacilityRegistrationForm, PatientForm, BillingForm, UserCreationWithRoleForm, UserEditForm, PrescriptionForm,
ServicePriceListForm)
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
from django.http import HttpResponseForbidden
from django.db import models
from django.utils import timezone
from DurielMedicApp.models import Appointment
from DurielEyeApp.models import EyeAppointment
from django.contrib.contenttypes.models import ContentType
from datetime import timedelta







def home_view(request):
    return render(request, "home.html")





# ---------- Role Checks ----------
def staff_check(user):
    return user.is_authenticated and user.role in ['ADMIN', 'DOCTOR', 'NURSE', 'OPTOMETRIST', 'PHYSIOTHERAPIST', 'RECEPTIONIST']

def admin_check(user):
    return user.is_authenticated and user.role == 'ADMIN'





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

#             # >>> Add these two lines <<<
#             from .utils import finalize_pending_login, log_login
#             finalize_pending_login(request)      # attaches pending login (if any) to this clinic
#             log_login(request, request.user)     # also log an explicit login-at-clinic selection

#             if clinic.clinic_type == 'GENERAL':
#                 return redirect('DurielMedicApp:dashboard')
#             elif clinic.clinic_type == 'EYE':
#                 return redirect('DurielEyeApp:eye_dashboard')
#             elif clinic.clinic_type == 'DENTAL':
#                 return redirect('DurielDentalApp:dental_dashboard')

#     return render(request, 'select-clinic/select_clinic.html', {
#         'clinics': user_clinics,
#         'clinic_types': dict(Clinic.CLINIC_TYPES)
#     })


@login_required
def select_clinic(request):
    user_clinics = request.user.clinic.all().order_by('clinic_type', 'name')
    today = timezone.now().date()
    can_renew = request.user.is_superuser or getattr(request.user, 'role', '') == 'ADMIN'

    clinics_enriched = []
    for c in user_clinics:
        end = getattr(c, 'subscription_end_date', None)
        days_left = (end - today).days if end else None
        is_expired = (getattr(c, 'is_subscription_active', True) is False) or (days_left is not None and days_left < 0)
        clinics_enriched.append({
            'clinic': c,
            'days_left': days_left,
            'is_expired': is_expired,
            'can_renew': can_renew,
            'renew_monthly_url': reverse('core:start_renewal', args=[c.id, 'MONTHLY']),
            'renew_yearly_url': reverse('core:start_renewal', args=[c.id, 'YEARLY']),
        })

    if request.method == 'POST':
        clinic_id = request.POST.get('clinic_id')
        clinic = Clinic.objects.filter(id=clinic_id, staff=request.user).first()
        if not clinic:
            messages.error(request, "You do not have access to this clinic.")
            return redirect('core:select_clinic')

        end = getattr(clinic, 'subscription_end_date', None)
        days_left = (end - today).days if end else None
        is_expired = (getattr(clinic, 'is_subscription_active', True) is False) or (days_left is not None and days_left < 0)
        if is_expired:
            messages.warning(request, "This clinic is expired. Please renew to continue.")
            return redirect('core:select_clinic')

        request.session['clinic_id'] = clinic.id
        request.session['clinic_type'] = clinic.clinic_type
        request.session['clinic_name'] = clinic.name

        from .utils import finalize_pending_login, log_login
        finalize_pending_login(request)
        log_login(request, request.user)

        if clinic.clinic_type == 'GENERAL':
            return redirect('DurielMedicApp:dashboard')
        elif clinic.clinic_type == 'EYE':
            return redirect('DurielEyeApp:eye_dashboard')
        elif clinic.clinic_type == 'DENTAL':
            return redirect('DurielDentalApp:dental_dashboard')

    primary_clinic_id = getattr(request.user, 'primary_clinic_id', None)
    active_count = sum(1 for x in clinics_enriched if not x['is_expired'])
    expired_count = len(clinics_enriched) - active_count
    has_multiple_clinics = len(clinics_enriched) > 1
    single_clinic = clinics_enriched[0] if len(clinics_enriched) == 1 else None

    return render(request, 'select-clinic/select_clinic.html', {
        'clinics': user_clinics,
        'clinics_enriched': clinics_enriched,
        'clinic_types': dict(Clinic.CLINIC_TYPES),
        'can_renew': can_renew,
        'primary_clinic_id': primary_clinic_id,
        'active_count': active_count,
        'expired_count': expired_count,
        'has_multiple_clinics': has_multiple_clinics,
        'single_clinic': single_clinic,
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

# @login_required
# def manage_user_roles(request):
#     # 🔹 Only superusers can see other superusers
#     if request.user.is_superuser:
#         users = CustomUser.objects.all()
#     else:
#         users = CustomUser.objects.filter(is_superuser=False)

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
def manage_user_roles(request):
    # 🔹 Superusers can see all users and clinics
    if request.user.is_superuser:
        users = CustomUser.objects.all()
        clinics = Clinic.objects.all()
    else:
        # 🔹 ADMIN users can only see users from their own clinics
        users = CustomUser.objects.filter(
            clinic__in=request.user.clinic.all(),
            is_superuser=False  # ADMINs can't see superusers
        )
        clinics = request.user.clinic.all()

    new_user_form = UserCreationWithRoleForm()
    new_user_form.fields['clinic'].queryset = clinics
    role_forms = {user.id: UserEditForm(instance=user) for user in users}

    if request.method == 'POST':
        if 'create_user' in request.POST:
            new_user_form = UserCreationWithRoleForm(request.POST)
            if new_user_form.is_valid():
                user = new_user_form.save(commit=False)
                
                # For non-superusers, ensure they can't create superusers
                if not request.user.is_superuser:
                    user.is_superuser = False
                
                user.save()
                new_user_form.save_m2m()  # Save many-to-many relationships
                
                return redirect('core:manage_roles')
        elif 'update_role' in request.POST:
            user_id = request.POST.get('user_id')
            user = get_object_or_404(CustomUser, id=user_id)
            role_form = UserEditForm(request.POST, instance=user)
            if role_form.is_valid():
                # For non-superusers, ensure they can't make users superusers
                if not request.user.is_superuser:
                    role_form.instance.is_superuser = False
                
                role_form.save()
                return redirect('core:manage_roles')

    return render(request, 'administration/manage_roles.html', {
        'users': users,
        'new_user_form': new_user_form,
        'role_forms': role_forms,
    })





# @login_required
# def edit_user_role(request, user_id):
#     user = get_object_or_404(CustomUser, id=user_id)
#     editing_self = (request.user.id == user.id)
    
#     if request.method == 'POST':
#         form = UserEditForm(request.POST, request.FILES, instance=user)
#         if form.is_valid():
#             # Prevent non-superusers from making superusers
#             if not request.user.is_superuser and form.cleaned_data.get('is_superuser'):
#                 messages.error(request, "Only superusers can create other superusers.")
#                 return redirect('core:manage_roles')
            
#             # Prevent users from deactivating themselves
#             if editing_self and not form.cleaned_data.get('is_active'):
#                 messages.error(request, "You cannot deactivate yourself.")
#                 return redirect('core:manage_roles')
                
#             form.save()

#             # ✅ Manual logging
#             from .utils import log_action
#             log_action(
#                 request,
#                 'UPDATE',
#                 user,
#                 details=f"Updated user role/details for {user.get_full_name() or user.username}"
#             )

#             messages.success(request, 'User details updated successfully.')
#             return redirect('core:manage_roles')
#     else:
#         form = UserEditForm(instance=user)
#         form.fields['clinic'].queryset = Clinic.objects.all()
        
#         # Hide superuser checkbox for non-superusers
#         if not request.user.is_superuser:
#             form.fields['is_superuser'].widget = forms.HiddenInput()

#     return render(request, 'dashboard/edit_user_role.html', {
#         'form': form,
#         'user_obj': user,
#         'editing_self': editing_self,
#     })



@login_required
def edit_user_role(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    editing_self = (request.user.id == user.id)

    # Permission checks
    if not request.user.is_superuser:
        if not user.clinic.filter(id__in=request.user.clinic.all()).exists():
            messages.error(request, "You don't have permission to edit this user.")
            return redirect('core:manage_roles')

    if request.method == 'POST':
        form = UserEditForm(request.POST, request.FILES, instance=user, request=request)
        if form.is_valid():
            if not request.user.is_superuser and form.cleaned_data.get('is_superuser'):
                messages.error(request, "Only superusers can create other superusers.")
                return redirect('core:manage_roles')

            if editing_self and not form.cleaned_data.get('is_active'):
                messages.error(request, "You cannot deactivate yourself.")
                return redirect('core:manage_roles')

            form.save()
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
        form = UserEditForm(instance=user, request=request)

        # ✅ Only override for superusers
        if request.user.is_superuser:
            form.fields['clinic'].queryset = Clinic.objects.all()

        # ✅ For admins, let UserEditForm logic handle merging
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



# @login_required
# @clinic_selected_required
# @role_required('ADMIN', 'RECEPTIONIST')
# def create_bill(request, patient_id=None):
#     clinic_id = request.session.get('clinic_id')
#     if not clinic_id:
#         messages.error(request, "No clinic selected.")
#         return redirect('select_clinic')

#     patients_with_appointments = Patient.objects.filter(clinic_id=clinic_id)
#     selected_patient_id = request.GET.get('patient')
#     patient = None
    
#     if selected_patient_id:
#         try:
#             patient = Patient.objects.get(patient_id=selected_patient_id, clinic_id=clinic_id)
#         except Patient.DoesNotExist:
#             pass
#     elif patient_id:
#         try:
#             patient = Patient.objects.get(pk=patient_id, clinic_id=clinic_id)
#         except Patient.DoesNotExist:
#             patient = None

#     if request.method == 'POST':
#         form = BillingForm(request.POST, clinic_id=clinic_id)
#         if form.is_valid():
#             bill = form.save(commit=False)
#             bill.created_by = request.user
#             bill.clinic = get_object_or_404(Clinic, id=clinic_id)
            
#             # Calculate total from selected services
#             selected_services = form.cleaned_data.get('services', [])
#             service_total = sum(service.price for service in selected_services)
            
#             # If amount was manually entered, add to service total
#             manual_amount = form.cleaned_data.get('amount', 0)
#             bill.amount = service_total + manual_amount
            
#             if not bill.paid_amount:
#                 bill.paid_amount = 0
                
#             if bill.paid_amount == bill.amount:
#                 bill.status = 'PAID'
#             elif bill.paid_amount > 0:
#                 bill.status = 'PARTIAL'
#             else:
#                 bill.status = 'PENDING'
                
#             bill.save()
#             form.save_m2m()  # Save the many-to-many services
            
#             log_action(
#                 request,
#                 'CREATE',
#                 bill,
#                 details=f"Created bill #{bill.id} for {bill.patient.full_name} - Amount: {bill.amount}"
#             )
            
#             messages.success(request, "Bill created successfully!")
#             return redirect('core:billing_list')
#     else:
#         form = BillingForm(initial={'service_date': date.today()}, clinic_id=clinic_id)
#         if patient:
#             form.initial['patient'] = patient.patient_id

#     appointment_id = request.GET.get('appointment_id')
#     if appointment_id:
#         appointment = Appointment.objects.filter(id=appointment_id, clinic_id=clinic_id).first()
#     elif patient:
#         appointment = Appointment.objects.filter(patient=patient, clinic_id=clinic_id).order_by('-date', '-start_time').first()
#     else:
#         appointment = None

#     return render(request, 'billing/billing_form.html', {
#         'form': form,
#         'patient': patient,
#         'patients_with_appointments': patients_with_appointments,
#         'appointment': appointment,
#         'selected_patient_id': selected_patient_id,
#     })


from datetime import date, timedelta

def get_latest_patient_appointment(patient, clinic_id):
    """Return the most recent appointment for a patient across all apps."""
    recent_date = date.today() - timedelta(days=30)

    from DurielEyeApp.models import EyeAppointment
    # from DurielPhysioApp.models import PhysioAppointment
    from DurielMedicApp.models import Appointment as GeneralAppointment

    appointments = []

    for model in [EyeAppointment, GeneralAppointment]:
        qs = model.objects.filter(patient=patient, clinic_id=clinic_id)
        today_appointments = qs.filter(date=date.today()).order_by('-start_time')
        recent_appointments = qs.filter(date__gte=recent_date).order_by('-date', '-start_time')
        any_appointment = qs.order_by('-date', '-start_time')

        if today_appointments.exists():
            appointments.append(today_appointments.first())
        elif recent_appointments.exists():
            appointments.append(recent_appointments.first())
        elif any_appointment.exists():
            appointments.append(any_appointment.first())

    if not appointments:
        return None

    # Return the appointment with the most recent date & start_time
    appointments.sort(key=lambda x: (x.date, getattr(x, 'start_time', 0)), reverse=True)
    return appointments[0]





@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def create_bill(request, patient_id=None):
    clinic_id = request.session.get('clinic_id')
    if not clinic_id:
        messages.error(request, "No clinic selected.")
        return redirect('select_clinic')

    patients_with_appointments = Patient.objects.filter(clinic_id=clinic_id)
    selected_patient_id = request.GET.get('patient')
    patient = None

    # --- Get patient ---
    if selected_patient_id:
        try:
            patient = Patient.objects.get(patient_id=selected_patient_id, clinic_id=clinic_id)
        except Patient.DoesNotExist:
            patient = None
    elif patient_id:
        try:
            patient = Patient.objects.get(pk=patient_id, clinic_id=clinic_id)
        except Patient.DoesNotExist:
            patient = None

    # --- Get appointment if specified ---
    appointment = None
    appointment_id = request.GET.get('appointment_id')
    appointment_type = request.GET.get('appointment_type')  # "general" or "eye"

    if appointment_id and appointment_type:
        try:
            if appointment_type == "eye":
                appointment = EyeAppointment.objects.get(id=appointment_id, clinic_id=clinic_id)
            else:
                appointment = Appointment.objects.get(id=appointment_id, clinic_id=clinic_id)
        except (Appointment.DoesNotExist, EyeAppointment.DoesNotExist):
            appointment = None

    # --- If no specific appointment but we have a patient, pick latest ---
    if patient and not appointment:
        appointment = get_latest_patient_appointment(patient, clinic_id)

    # --- Handle AJAX (used for patient selection updates) ---
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        context = {
            'appointment': appointment,
            'patient': patient
        }
        return render(request, 'billing/_appointment_info.html', context)

    # --- Handle Form Submission ---
    if request.method == 'POST':
        form = BillingForm(request.POST, clinic_id=clinic_id)
        if form.is_valid():
            bill = form.save(commit=False)
            bill.created_by = request.user
            bill.clinic = get_object_or_404(Clinic, id=clinic_id)
            bill.patient = form.cleaned_data['patient']

            # Handle appointment (from hidden fields)
            appointment_id_from_form = request.POST.get('appointment_id')
            appointment_type_from_form = request.POST.get('appointment_type')

            if appointment_id_from_form and appointment_type_from_form:
                try:
                    if appointment_type_from_form == "eye":
                        appointment = EyeAppointment.objects.get(id=appointment_id_from_form, clinic_id=clinic_id)
                    else:
                        appointment = Appointment.objects.get(id=appointment_id_from_form, clinic_id=clinic_id)

                    # Link using GenericForeignKey
                    bill.appointment_object_id = appointment.id
                    bill.appointment_content_type = ContentType.objects.get_for_model(appointment)

                except (Appointment.DoesNotExist, EyeAppointment.DoesNotExist):
                    appointment = None

            # --- Calculate billing amount ---
            selected_services = form.cleaned_data.get('services')
            if selected_services:
                bill.amount = sum(service.price for service in selected_services)
            else:
                bill.amount = form.cleaned_data.get('amount', 0)

            if not bill.paid_amount:
                bill.paid_amount = 0

            # --- Set status ---
            if bill.paid_amount >= bill.amount and bill.amount > 0:
                bill.status = 'PAID'
            elif bill.paid_amount > 0:
                bill.status = 'PARTIAL'
            else:
                bill.status = 'PENDING'

            bill.save()
            form.save_m2m()

            log_action(
                request,
                'CREATE',
                bill,
                details=f"Created bill #{bill.id} for {bill.patient.full_name} - Amount: {bill.amount}"
            )

            messages.success(request, f"Bill created successfully! Bill ID: #{bill.id}")
            return redirect('core:view_bill', pk=bill.pk)
    else:
        # --- Initial form data ---
        initial_data = {'service_date': date.today()}
        if patient:
            initial_data['patient'] = patient.patient_id
        form = BillingForm(initial=initial_data, clinic_id=clinic_id)

    context = {
        'form': form,
        'patient': patient,
        'patients_with_appointments': patients_with_appointments,
        'appointment': appointment,
        'selected_patient_id': selected_patient_id,
        'title': 'Create New Bill'
    }

    return render(request, 'billing/billing_form.html', context)




# @login_required
# @clinic_selected_required
# @role_required('ADMIN', 'RECEPTIONIST')
# def create_bill(request, patient_id=None):
#     clinic_id = request.session.get('clinic_id')
#     if not clinic_id:
#         messages.error(request, "No clinic selected.")
#         return redirect('select_clinic')

#     patients_with_appointments = Patient.objects.filter(clinic_id=clinic_id)
#     selected_patient_id = request.GET.get('patient')
#     patient = None
    
#     # Try to get patient by patient_id (not pk)
#     if selected_patient_id:
#         try:
#             patient = Patient.objects.get(patient_id=selected_patient_id, clinic_id=clinic_id)
#         except Patient.DoesNotExist:
#             print(f"Patient with ID {selected_patient_id} not found")
#     elif patient_id:
#         try:
#             patient = Patient.objects.get(pk=patient_id, clinic_id=clinic_id)
#         except Patient.DoesNotExist:
#             patient = None

#     # Get appointment - improved logic
#     appointment_id = request.GET.get('appointment_id')
#     appointment = None
    
#     if appointment_id:
#         try:
#             appointment = Appointment.objects.get(id=appointment_id, clinic_id=clinic_id)
#         except Appointment.DoesNotExist:
#             appointment = None
    
#     # If no specific appointment but we have a patient, find the most relevant appointment
#     if patient and not appointment:
#         from datetime import timedelta
#         recent_date = date.today() - timedelta(days=30)
        
#         # First try today's appointments
#         appointment = Appointment.objects.filter(
#             patient=patient, 
#             clinic_id=clinic_id,
#             date=date.today()
#         ).order_by('-start_time').first()
        
#         # If no appointment today, get the most recent one within 30 days
#         if not appointment:
#             appointment = Appointment.objects.filter(
#                 patient=patient, 
#                 clinic_id=clinic_id,
#                 date__gte=recent_date
#             ).order_by('-date', '-start_time').first()
        
#         # If still no appointment, get any appointment for this patient
#         if not appointment:
#             appointment = Appointment.objects.filter(
#                 patient=patient,
#                 clinic_id=clinic_id
#             ).order_by('-date', '-start_time').first()

#         print(f"Found appointment for {patient.full_name}: {appointment}")

#     # Handle AJAX requests for patient selection
#     if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
#         print(f"AJAX request for patient: {patient.full_name if patient else None}")
#         print(f"Found appointment: {appointment}")
        
#         context = {
#             'appointment': appointment,
#             'patient': patient
#         }
#         return render(request, 'billing/_appointment_info.html', context)

#     # Rest of your view code...

#     if request.method == 'POST':
#         form = BillingForm(request.POST, clinic_id=clinic_id)
#         if form.is_valid():
#             bill = form.save(commit=False)
#             bill.created_by = request.user
#             bill.clinic = get_object_or_404(Clinic, id=clinic_id)

#             # appointment_id comes from hidden input
#             appointment_id_from_form = request.POST.get('appointment_id')
#             if appointment_id_from_form:
#                 try:
#                     bill.appointment = Appointment.objects.get(
#                         id=appointment_id_from_form, 
#                         clinic_id=clinic_id
#                     )
#                 except Appointment.DoesNotExist:
#                     bill.appointment = None

#             # bill.patient is already set via form.cleaned_data
#             bill.patient = form.cleaned_data['patient']

#             # calculate total from services if selected
#             selected_services = form.cleaned_data.get('services')
#             if selected_services:
#                 bill.amount = sum(service.price for service in selected_services)
#             else:
#                 bill.amount = form.cleaned_data.get('amount', 0)

#             if not bill.paid_amount:
#                 bill.paid_amount = 0

#             # set status
#             if bill.paid_amount >= bill.amount and bill.amount > 0:
#                 bill.status = 'PAID'
#             elif bill.paid_amount > 0:
#                 bill.status = 'PARTIAL'
#             else:
#                 bill.status = 'PENDING'

#             bill.save()
#             form.save_m2m()

            
#             log_action(
#                 request,
#                 'CREATE',
#                 bill,
#                 details=f"Created bill #{bill.id} for {bill.patient.full_name} - Amount: {bill.amount}"
#             )
            
#             messages.success(request, f"Bill created successfully! Bill ID: #{bill.id}")
#             return redirect('core:view_bill', pk=bill.pk)
#     else:
#         initial_data = {'service_date': date.today()}
#         if patient:
#             initial_data['patient'] = patient.patient_id
#         form = BillingForm(initial=initial_data, clinic_id=clinic_id)

#     context = {
#         'form': form,
#         'patient': patient,
#         'patients_with_appointments': patients_with_appointments,
#         'appointment': appointment,
#         'selected_patient_id': selected_patient_id,
#         'title': 'Create New Bill'
#     }
    
#     return render(request, 'billing/billing_form.html', context)
    
    
    



@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def edit_bill(request, pk):
    bill = get_object_or_404(Billing, pk=pk)
    clinic_id = request.session.get('clinic_id')
    
    if request.method == 'POST':
        form = BillingForm(request.POST, instance=bill, clinic_id=clinic_id)
        if form.is_valid():
            updated_bill = form.save(commit=False)
            
            # Calculate total from selected services
            selected_services = form.cleaned_data.get('services', [])
            service_total = sum(service.price for service in selected_services)
            
            # If amount was manually entered, add to service total
            manual_amount = form.cleaned_data.get('amount', 0)
            updated_bill.amount = service_total + manual_amount
            
            if updated_bill.paid_amount > updated_bill.amount:
                messages.error(request, "Paid amount cannot be greater than total amount")
                return render(request, 'billing/billing_form.html', {
                    'form': form, 
                    'bill': bill,
                    'patients_with_appointments': Patient.objects.filter(clinic_id=clinic_id)
                })
            
            if updated_bill.paid_amount == updated_bill.amount:
                updated_bill.status = 'PAID'
            elif updated_bill.paid_amount > 0:
                updated_bill.status = 'PARTIAL'
            else:
                updated_bill.status = 'PENDING'
            
            updated_bill.save()
            form.save_m2m()  # Save the many-to-many services
            
            log_action(
                request,
                'UPDATE',
                updated_bill,
                details=f"Updated bill #{updated_bill.id} for {updated_bill.patient.full_name}"
            )
            
            messages.success(request, "Bill updated successfully!")
            return redirect('core:view_bill', pk=bill.pk)
    else:
        form = BillingForm(instance=bill, clinic_id=clinic_id)
        if bill.services.exists():
            form.initial['services'] = bill.services.all()
    
    patients_with_appointments = Patient.objects.filter(clinic_id=clinic_id)
    
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






# @login_required
# @clinic_selected_required
# @role_required('ADMIN', 'RECEPTIONIST')
# def generate_receipt(request, pk):
#     bill = get_object_or_404(Billing, pk=pk)
#     payments = bill.payments.all().order_by('-payment_date')

#     if payments.exists():
#         payment = payments.first()  # latest payment
#     else:
#         payment = None

#     context = {
#         'bill': bill,
#         'payment': payment,
#         'payments': payments,
#         'outstanding': bill.amount - bill.paid_amount,
#         'today': timezone.now().date()
#     }

#     return render(request, 'billing/receipt.html', context)



@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def generate_receipt(request, pk):
    bill = get_object_or_404(Billing, pk=pk)
    payments = bill.payments.all().order_by('-payment_date')
    payment = payments.first() if payments.exists() else None

    clinic_obj = getattr(bill, 'clinic', None)
    clinic_name = (
        getattr(clinic_obj, 'name', None)
        or request.session.get('clinic_name')
        or (getattr(getattr(request.user, 'primary_clinic', None), 'name', None) if request.user.is_authenticated else None)
        or 'Your Clinic'
    )

    context = {
        'bill': bill,
        'payment': payment,
        'payments': payments,
        'outstanding': bill.amount - bill.paid_amount,
        'today': timezone.now().date(),
        'clinic_name': clinic_name,
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
@user_passes_test(lambda u: u.is_superuser)
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
    user_clinic = request.GET.get('user_clinic', '')
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
    if user_clinic:
        users = users.filter(clinic__name__icontains=user_clinic).distinct()  
    
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
        'user_clinic': user_clinic,
        'clinic_search': clinic_search,
        'user_search': user_search,
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
@clinic_selected_required
@role_required('ADMIN', 'DOCTOR', 'OPTOMETRIST')
def add_prescription(request, patient_id):
    """Add prescription with inventory integration and logging."""
    patient = get_object_or_404(Patient, patient_id=patient_id)
    clinic_id = request.session.get('clinic_id')
    clinic = get_object_or_404(Clinic, id=clinic_id)

    # Get active medications for this clinic
    medications = ClinicMedication.objects.filter(
        clinic=clinic,
        status='ACTIVE'
    ).order_by('name')

    if request.method == 'POST':
        # Use PrescriptionForm to handle validation
        form = PrescriptionForm(request.POST, clinic=clinic)
        if form.is_valid():
            prescription = form.save(commit=False)
            prescription.patient = patient
            prescription.clinic = clinic
            prescription.prescribed_by = request.user
            prescription.save()

            log_action(
                request,
                'CREATE',
                prescription,
                details=f"Added prescription for {patient.full_name}: "
                        f"{prescription.clinic_medication.name if prescription.clinic_medication else prescription.custom_medication}"
            )

            messages.success(request, "Prescription saved successfully!")

            # Optional: notify about stock if clinic medication is used
            if prescription.clinic_medication:
                messages.info(
                    request,
                    f"Would you like to dispense this medication now? "
                    f"Available stock: {prescription.clinic_medication.quantity_in_stock}"
                )

            return redirect('core:patient_detail', pk=patient.patient_id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PrescriptionForm(clinic=clinic, initial={'patient': patient})

    return render(request, 'prescription/add_prescription.html', {
        'form': form,
        'patient': patient,
        'clinic': clinic,
        'medications': medications
    })


@login_required
def edit_prescription(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk)
    patient = prescription.patient

    # Ensure the user belongs to the clinic of this prescription
    if prescription.clinic not in request.user.clinic.all():
        return HttpResponseForbidden("You do not have permission to access this page.")

    # Get medications for the current clinic to populate the dropdown
    clinic_id = request.session.get('clinic_id')
    medications = ClinicMedication.objects.filter(
        clinic_id=clinic_id,
        status='ACTIVE'
    ).order_by('name')

    # Pass the current medication ID to template for pre-selection
    current_medication_id = prescription.clinic_medication.id if prescription.clinic_medication else None

    if request.method == 'POST':
        medication_id = request.POST.get('medication')
        
        try:
            medication = ClinicMedication.objects.get(id=medication_id, clinic_id=clinic_id)
        except ClinicMedication.DoesNotExist:
            messages.error(request, "Invalid medication selected.")
            return redirect('core:patient_detail', pk=patient.patient_id)
        
        # Update prescription
        prescription.clinic_medication = medication
        prescription.dosage = request.POST.get('dosage')
        prescription.instructions = request.POST.get('instructions')
        prescription.save()

        log_action(
            request,
            'UPDATE',
            prescription,
            details=f"Updated prescription for {patient.full_name}"
        )
        messages.success(request, "Prescription updated successfully.")
        return redirect('core:patient_detail', pk=patient.patient_id)

    return render(request, 'prescription/edit_prescription.html', {
        'prescription': prescription,
        'patient': patient,
        'medications': medications,
        'current_medication_id': current_medication_id,
    })


# @login_required
# def edit_prescription(request, pk):
#     prescription = get_object_or_404(Prescription, pk=pk)
#     patient = prescription.patient

#     # Ensure the user belongs to the clinic of this prescription
#     if prescription.clinic not in request.user.clinic.all():
#         return HttpResponseForbidden("You do not have permission to access this page.")

#     # Get medications for the current clinic to populate the dropdown
#     user_clinics = request.user.clinic.all()
#     medications = ClinicMedication.objects.filter(
#         clinic__in=user_clinics,
#         status='ACTIVE'
#     ).order_by('name')

#     # Pass the current medication ID to template for pre-selection
#     current_medication_id = prescription.clinic_medication.id if prescription.clinic_medication else None

#     if request.method == 'POST':
#         medication_id = request.POST.get('medication')
        
#         try:
#             medication = ClinicMedication.objects.get(id=medication_id, clinic__in=user_clinics)
#         except ClinicMedication.DoesNotExist:
#             messages.error(request, "Invalid medication selected.")
#             return redirect('core:patient_detail', pk=patient.patient_id)
        
#         # Update prescription
#         prescription.clinic_medication = medication
#         prescription.dosage = request.POST.get('dosage')
#         prescription.instructions = request.POST.get('instructions')
#         prescription.save()

#         log_action(
#             request,
#             'UPDATE',
#             prescription,
#             details=f"Updated prescription for {patient.full_name}"
#         )
#         messages.success(request, "Prescription updated successfully.")
#         return redirect('core:patient_detail', pk=patient.patient_id)

#     return render(request, 'prescription/edit_prescription.html', {
#         'prescription': prescription,
#         'patient': patient,
#         'medications': medications,
#         'current_medication_id': current_medication_id,
#     })


# @login_required
# def prescription_list(request):
#     clinic_id = request.session.get('clinic_id')
#     if not clinic_id:
#         messages.error(request, "No clinic selected. Please select a clinic first.")
#         return redirect('core:select_clinic')

#     query = request.GET.get('q', '')
#     prescriptions = Prescription.objects.filter(patient__clinic_id=clinic_id).select_related('patient', 'prescribed_by')

#     if query:
#         prescriptions = prescriptions.filter(
#             Q(patient__full_name__icontains=query) |
#             Q(prescribed_by__first_name__icontains=query) |
#             Q(prescribed_by__last_name__icontains=query) |
#             Q(medication__icontains=query) |
#             Q(date_prescribed__icontains=query)
#         )

#     context = {
#         'prescriptions': prescriptions.order_by('-date_prescribed'),
#         'query': query,
#     }
#     return render(request, 'prescription/prescription_list.html', context)


@login_required
def prescription_list(request):
    clinic_id = request.session.get('clinic_id')
    if not clinic_id:
        messages.error(request, "No clinic selected. Please select a clinic first.")
        return redirect('core:select_clinic')

    query = request.GET.get('q', '')
    # Explicitly order by date_prescribed in descending order (newest first)
    prescriptions = Prescription.objects.filter(
        patient__clinic_id=clinic_id
    ).select_related(
        'patient', 'prescribed_by', 'clinic_medication'
    ).order_by('-date_prescribed', '-id')  # Added secondary ordering by ID for consistency

    if query:
        prescriptions = prescriptions.filter(
            Q(patient__full_name__icontains=query) |
            Q(prescribed_by__first_name__icontains=query) |
            Q(prescribed_by__last_name__icontains=query) |
            Q(clinic_medication__name__icontains=query) |
            Q(date_prescribed__icontains=query)
        )

    # Pagination - 25 items per page
    paginator = Paginator(prescriptions, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'prescriptions': page_obj,
        'query': query,
    }
    return render(request, 'prescription/prescription_list.html', context)


@login_required
def prescription_menu(request):
    buttons = [
        # {"name": "Add Prescription", "url": "add_prescription"},
        # {"name": "Edit Prescription", "url": "edit_prescription"},
        {"name": "Prescription List", "url": "core:prescription_list"},
        # {"name": "Deactivate Prescription", "url": "deactivate_prescription"},
        # {"name": "Delete Prescription", "url": "delete_prescription"},
        # {"name": "Enhanced Add Prescription", "url": "enhanced_add_prescription"},
        # {"name": "Dispense Prescription", "url": "dispense_prescription"},
        {"name": "Inventory Dashboard", "url": "core:inventory_dashboard"},
        {"name": "Medications List", "url": "core:medication_list"},
        {"name": "Add Medication", "url": "core:add_medication"},
        # {"name": "Edit Medication", "url": "edit_medication"},
        # {"name": "Medication Detail", "url": "medication_detail"},
        # {"name": "Adjust Stock", "url": "adjust_stock"},
        # {"name": "Stock Movements", "url": "stock_movements"},
        {"name": "Manage Categories", "url": "core:manage_categories"},
    ]
    return render(request, "prescription/prescription_menu.html", {"buttons": buttons})



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



# Add these views to your existing views.py

import csv
from io import TextIOWrapper
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.db.models import Q, Sum
from django.http import JsonResponse
from datetime import date, timedelta
from .models import ClinicMedication, MedicationCategory, StockMovement
from .forms import ClinicMedicationForm, StockAdjustmentForm, BulkStockUploadForm, MedicationCategoryForm
from core.decorators import clinic_selected_required
from .utils import log_action
from django.db.models import F


# ---------- INVENTORY MANAGEMENT ----------

@login_required
@clinic_selected_required
@role_required('ADMIN', 'DOCTOR', 'RECEPTIONIST')
def inventory_dashboard(request):
    """Main inventory dashboard with key metrics"""
    clinic_id = request.session.get('clinic_id')
    clinic = get_object_or_404(Clinic, id=clinic_id)
    
    # Get inventory statistics
    total_medications = ClinicMedication.objects.filter(clinic=clinic, status='ACTIVE').count()
    out_of_stock = ClinicMedication.objects.filter(clinic=clinic, quantity_in_stock=0, status='ACTIVE').count()
    low_stock = ClinicMedication.objects.filter(
        clinic=clinic, 
        quantity_in_stock__lte=F('minimum_stock_level'),
        quantity_in_stock__gt=0,
        status='ACTIVE'
    ).count()
    
    # Low stock alerts
    low_stock_items = ClinicMedication.objects.filter(
        clinic=clinic,
        quantity_in_stock__lte=F('minimum_stock_level'),
        status='ACTIVE'
    ).order_by('quantity_in_stock')[:10]
    
    # Expiring soon (within 30 days)
    expiring_soon = ClinicMedication.objects.filter(
        clinic=clinic,
        expiry_date__lte=date.today() + timedelta(days=30),
        expiry_date__gte=date.today(),
        status='ACTIVE'
    ).order_by('expiry_date')[:10]
    
    # Recent stock movements
    recent_movements = StockMovement.objects.filter(
        medication__clinic=clinic
    ).select_related('medication', 'created_by').order_by('-created_at')[:10]
    
    context = {
        'clinic': clinic,
        'total_medications': total_medications,
        'out_of_stock_count': out_of_stock,
        'low_stock_count': low_stock,
        'low_stock_items': low_stock_items,
        'expiring_soon': expiring_soon,
        'recent_movements': recent_movements,
    }
    
    return render(request, 'inventory/dashboard.html', context)




# @login_required
# @clinic_selected_required
# @role_required('ADMIN', 'DOCTOR', 'RECEPTIONIST')
# def inventory_dashboard(request):
#     """Main inventory dashboard with key metrics"""
#     clinic_id = request.session.get('clinic_id')
#     clinic = get_object_or_404(Clinic, id=clinic_id)
    
#     # Get inventory statistics
#     total_medications = ClinicMedication.objects.filter(clinic=clinic, status='ACTIVE').count()
#     out_of_stock = ClinicMedication.objects.filter(clinic=clinic, quantity_in_stock=0, status='ACTIVE').count()
#     low_stock = ClinicMedication.objects.filter(
#         clinic=clinic, 
#         # quantity_in_stock__lte=models.F('minimum_stock_level'),
#         quantity_in_stock__lte=F('minimum_stock_level'),
#         quantity_in_stock__gt=0,
#         status='ACTIVE'
#     ).count()
    
#     # Recently added medications
#     recent_medications = ClinicMedication.objects.filter(clinic=clinic).order_by('-created_at')[:5]
    
#     # Low stock alerts
#     low_stock_items = ClinicMedication.objects.filter(
#         clinic=clinic,
#         quantity_in_stock__lte=F('minimum_stock_level'),
#         status='ACTIVE'
#     ).order_by('quantity_in_stock')[:10]
    
#     # Expiring soon (within 30 days)
#     expiring_soon = ClinicMedication.objects.filter(
#         clinic=clinic,
#         expiry_date__lte=date.today() + timedelta(days=30),
#         expiry_date__gte=date.today(),
#         status='ACTIVE'
#     ).order_by('expiry_date')[:10]
    
#     context = {
#         'clinic': clinic,
#         'total_medications': total_medications,
#         'out_of_stock_count': out_of_stock,
#         'low_stock_count': low_stock,
#         'recent_medications': recent_medications,
#         'low_stock_items': low_stock_items,
#         'expiring_soon': expiring_soon,
#     }
    
#     return render(request, 'inventory/dashboard.html', context)




# Update your medication_list view to filter categories by clinic:

@login_required
@clinic_selected_required
@role_required('ADMIN', 'DOCTOR', 'RECEPTIONIST')
def medication_list(request):
    """List all medications for the current clinic"""
    clinic_id = request.session.get('clinic_id')
    clinic = get_object_or_404(Clinic, id=clinic_id)
    
    medications = ClinicMedication.objects.filter(clinic=clinic).order_by('name')
    
    # Search and filtering
    search = request.GET.get('search', '')
    category_filter = request.GET.get('category', '')
    stock_filter = request.GET.get('stock_status', '')
    
    if search:
        medications = medications.filter(
            Q(name__icontains=search) |
            Q(generic_name__icontains=search) |
            Q(manufacturer__icontains=search)
        )
    
    if category_filter:
        medications = medications.filter(category_id=category_filter)
    
    if stock_filter == 'out_of_stock':
        medications = medications.filter(quantity_in_stock=0)
    elif stock_filter == 'low_stock':
        medications = medications.filter(
            quantity_in_stock__lte=F('minimum_stock_level'),
            quantity_in_stock__gt=0
        )
    elif stock_filter == 'in_stock':
        medications = medications.filter(quantity_in_stock__gt=F('minimum_stock_level'))
    
    # Only show categories for this clinic
    categories = MedicationCategory.objects.filter(clinic=clinic)
    
    context = {
        'medications': medications,
        'categories': categories,
        'search': search,
        'category_filter': category_filter,
        'stock_filter': stock_filter,
        'clinic': clinic,
    }
    
    return render(request, 'inventory/medication_list.html', context)

# @login_required
# @clinic_selected_required
# @role_required('ADMIN', 'DOCTOR', 'RECEPTIONIST')
# def medication_list(request):
#     """List all medications for the current clinic"""
#     clinic_id = request.session.get('clinic_id')
#     clinic = get_object_or_404(Clinic, id=clinic_id)
    
#     medications = ClinicMedication.objects.filter(clinic=clinic).order_by('name')
    
#     # Search and filtering
#     search = request.GET.get('search', '')
#     category_filter = request.GET.get('category', '')
#     stock_filter = request.GET.get('stock_status', '')
    
#     if search:
#         medications = medications.filter(
#             Q(name__icontains=search) |
#             Q(generic_name__icontains=search) |
#             Q(manufacturer__icontains=search)
#         )
    
#     if category_filter:
#         medications = medications.filter(category_id=category_filter)
    
#     if stock_filter == 'out_of_stock':
#         medications = medications.filter(quantity_in_stock=0)
#     elif stock_filter == 'low_stock':
#         medications = medications.filter(
#             quantity_in_stock__lte=models.F('minimum_stock_level'),
#             quantity_in_stock__gt=0
#         )
#     elif stock_filter == 'in_stock':
#         medications = medications.filter(quantity_in_stock__gt=models.F('minimum_stock_level'))
    
#     categories = MedicationCategory.objects.all()
    
#     context = {
#         'medications': medications,
#         'categories': categories,
#         'search': search,
#         'category_filter': category_filter,
#         'stock_filter': stock_filter,
#         'clinic': clinic,
#     }
    
#     return render(request, 'inventory/medication_list.html', context)


@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def add_medication(request):
    """Add new medication to clinic inventory"""
    clinic_id = request.session.get('clinic_id')
    clinic = get_object_or_404(Clinic, id=clinic_id)
    
    if request.method == 'POST':
        form = ClinicMedicationForm(request.POST, clinic=clinic)
        if form.is_valid():
            medication = form.save(commit=False)
            medication.clinic = clinic
            medication.added_by = request.user
            medication.save()
            
            # Log initial stock if any
            if medication.quantity_in_stock > 0:
                StockMovement.objects.create(
                    medication=medication,
                    movement_type='IN',
                    quantity=medication.quantity_in_stock,
                    previous_stock=0,
                    new_stock=medication.quantity_in_stock,
                    created_by=request.user,
                    notes="Initial stock entry"
                )
            
            log_action(
                request,
                'CREATE',
                medication,
                details=f"Added medication: {medication.display_name}"
            )
            
            messages.success(request, f"Medication '{medication.display_name}' added successfully!")
            return redirect('core:medication_list')
    else:
        form = ClinicMedicationForm(clinic=clinic)
    
    return render(request, 'inventory/add_medication.html', {'form': form, 'clinic': clinic})


@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def edit_medication(request, pk):
    """Edit existing medication"""
    clinic_id = request.session.get('clinic_id')
    medication = get_object_or_404(ClinicMedication, pk=pk, clinic_id=clinic_id)
    
    if request.method == 'POST':
        form = ClinicMedicationForm(request.POST, instance=medication, clinic=medication.clinic)
        if form.is_valid():
            form.save()
            
            log_action(
                request,
                'UPDATE',
                medication,
                details=f"Updated medication: {medication.display_name}"
            )
            
            messages.success(request, f"Medication '{medication.display_name}' updated successfully!")
            return redirect('core:medication_list')
    else:
        form = ClinicMedicationForm(instance=medication, clinic=medication.clinic)
    
    return render(request, 'inventory/edit_medication.html', {
        'form': form, 
        'medication': medication
    })
    
    
    
import csv
from django.http import HttpResponse

@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def export_medications_csv(request):
    clinic_id = request.session.get('clinic_id')
    medications = ClinicMedication.objects.filter(clinic_id=clinic_id)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="medications_report.csv"'

    writer = csv.writer(response)
    writer.writerow(['Name', 'Category', 'Stock', 'Unit Price (₦)', 'Total Price (₦)', 'Expiry'])

    for med in medications:
        total_price = (med.selling_price or 0) * (med.quantity_in_stock or 0)
        writer.writerow([
            med.display_name,
            med.category.name if med.category else '',
            med.quantity_in_stock,
            f"{med.selling_price:.2f}" if med.selling_price else "0.00",
            f"{total_price:.2f}",
            med.expiry_date.strftime("%Y-%m-%d") if med.expiry_date else ''
        ])

    return response



@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def adjust_stock(request, pk):
    """Adjust stock levels for a medication"""
    clinic_id = request.session.get('clinic_id')
    medication = get_object_or_404(ClinicMedication, pk=pk, clinic_id=clinic_id)
    
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        if form.is_valid():
            adjustment_type = form.cleaned_data['adjustment_type']
            quantity = form.cleaned_data['quantity']
            notes = form.cleaned_data['notes']
            
            old_stock = medication.quantity_in_stock
            
            if adjustment_type == 'ADD':
                new_stock = old_stock + quantity
                movement_type = 'IN'
                movement_quantity = quantity
            elif adjustment_type == 'REMOVE':
                new_stock = max(0, old_stock - quantity)
                movement_type = 'OUT'
                movement_quantity = -min(quantity, old_stock)
            else:  # SET
                new_stock = quantity
                movement_type = 'ADJUSTMENT'
                movement_quantity = new_stock - old_stock
            
            medication.quantity_in_stock = new_stock
            medication.save()
            
            # Create stock movement record
            StockMovement.objects.create(
                medication=medication,
                movement_type=movement_type,
                quantity=movement_quantity,
                previous_stock=old_stock,
                new_stock=new_stock,
                created_by=request.user,
                notes=notes or f"Stock {adjustment_type.lower()}"
            )
            
            log_action(
                request,
                'UPDATE',
                medication,
                details=f"Stock adjustment for {medication.display_name}: {old_stock} → {new_stock}"
            )
            
            messages.success(request, f"Stock adjusted successfully! New stock: {new_stock}")
            return redirect('core:medication_list')
    else:
        form = StockAdjustmentForm()
    
    return render(request, 'inventory/adjust_stock.html', {
        'form': form,
        'medication': medication
    })


@login_required
@clinic_selected_required
@role_required('ADMIN', 'DOCTOR', 'RECEPTIONIST')
def stock_movements(request, pk):
    """View stock movement history for a medication"""
    clinic_id = request.session.get('clinic_id')
    medication = get_object_or_404(ClinicMedication, pk=pk, clinic_id=clinic_id)
    movements = medication.stock_movements.all().order_by('-created_at')
    
    return render(request, 'inventory/stock_movements.html', {
        'medication': medication,
        'movements': movements
    })


@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def bulk_upload_stock(request):
    """Bulk upload medications via CSV"""
    clinic_id = request.session.get('clinic_id')
    clinic = get_object_or_404(Clinic, id=clinic_id)
    
    if request.method == 'POST':
        form = BulkStockUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            overwrite = form.cleaned_data['overwrite_existing']
            
            try:
                # Process CSV file
                file_data = TextIOWrapper(csv_file.file, encoding='utf-8')
                csv_reader = csv.DictReader(file_data)
                
                created_count = 0
                updated_count = 0
                errors = []
                
                for row_num, row in enumerate(csv_reader, start=2):
                    try:
                        name = row.get('name', '').strip()
                        strength = row.get('strength', '').strip()
                        
                        if not name:
                            errors.append(f"Row {row_num}: Missing medication name")
                            continue
                        
                        # Check if medication exists
                        medication, created = ClinicMedication.objects.get_or_create(
                            clinic=clinic,
                            name=name,
                            strength=strength,
                            defaults={
                                'quantity_in_stock': int(row.get('quantity', 0) or 0),
                                'cost_price': float(row.get('cost_price', 0) or 0),
                                'selling_price': float(row.get('selling_price', 0) or 0),
                                'expiry_date': row.get('expiry_date') or None,
                                'added_by': request.user,
                            }
                        )
                        
                        if created:
                            created_count += 1
                            # Log initial stock
                            if medication.quantity_in_stock > 0:
                                StockMovement.objects.create(
                                    medication=medication,
                                    movement_type='IN',
                                    quantity=medication.quantity_in_stock,
                                    previous_stock=0,
                                    new_stock=medication.quantity_in_stock,
                                    created_by=request.user,
                                    notes="Bulk upload"
                                )
                        elif overwrite:
                            # Update existing medication
                            old_stock = medication.quantity_in_stock
                            new_quantity = int(row.get('quantity', 0) or 0)
                            
                            medication.quantity_in_stock = new_quantity
                            medication.cost_price = float(row.get('cost_price', 0) or 0)
                            medication.selling_price = float(row.get('selling_price', 0) or 0)
                            if row.get('expiry_date'):
                                medication.expiry_date = row.get('expiry_date')
                            medication.save()
                            
                            # Log stock change
                            if old_stock != new_quantity:
                                StockMovement.objects.create(
                                    medication=medication,
                                    movement_type='ADJUSTMENT',
                                    quantity=new_quantity - old_stock,
                                    previous_stock=old_stock,
                                    new_stock=new_quantity,
                                    created_by=request.user,
                                    notes="Bulk upload update"
                                )
                            
                            updated_count += 1
                    
                    except (ValueError, KeyError) as e:
                        errors.append(f"Row {row_num}: {str(e)}")
                        continue
                
                # Show results
                if created_count or updated_count:
                    success_msg = f"Bulk upload completed! Created: {created_count}, Updated: {updated_count}"
                    if errors:
                        success_msg += f". {len(errors)} errors occurred."
                    messages.success(request, success_msg)
                
                if errors:
                    for error in errors[:5]:  # Show first 5 errors
                        messages.error(request, error)
                    if len(errors) > 5:
                        messages.error(request, f"... and {len(errors) - 5} more errors")
                
                return redirect('core:medication_list')
                
            except Exception as e:
                messages.error(request, f"Error processing CSV file: {str(e)}")
    else:
        form = BulkStockUploadForm()
    
    return render(request, 'inventory/bulk_upload.html', {'form': form})


from django.db.models import Sum
from django.utils import timezone

@login_required
@clinic_selected_required
@role_required('ADMIN', 'DOCTOR', 'RECEPTIONIST')
def dispense_prescription(request, pk):
    """Dispense prescription, deduct stock, and add to billing."""
    prescription = get_object_or_404(Prescription, pk=pk)
    patient = prescription.patient

    if not prescription.clinic_medication:
        messages.error(request, "This prescription is not from clinic inventory and cannot be dispensed.")
        return redirect('core:prescription_list')

    if prescription.stock_deducted:
        messages.info(request, "This prescription has already been dispensed.")
        return redirect('core:prescription_list')

    if request.method == 'POST':
        # Deduct stock
        success = prescription.deduct_stock()
        if success:
            price = (prescription.clinic_medication.selling_price or 0) * prescription.quantity_prescribed

            # Build description string
            description = (
                f"Dispensed: {prescription.medication_name} x{prescription.quantity_prescribed} "
                f"(₦{prescription.clinic_medication.selling_price})"
            )

            # Create billing record
            Billing.objects.create(
                patient=patient,
                clinic=prescription.clinic,
                amount=price,
                service_date=timezone.now().date(),
                description=description,
                created_by=request.user
            )

            # Log action
            log_action(
                request,
                'UPDATE',
                prescription,
                details=f"Dispensed prescription for {patient.full_name}: {description}"
            )

            # Calculate total billed dynamically
            total_billed = Billing.objects.filter(patient=patient).aggregate(Sum('amount'))['amount__sum'] or 0

            messages.success(
                request,
                f"Prescription dispensed! Stock deducted, ₦{price} added to billing. "
                f"Total billed for {patient.full_name}: ₦{total_billed}"
            )
        else:
            messages.error(request, "Insufficient stock to dispense this prescription.")

        # Reload from DB to confirm stock update
        prescription.refresh_from_db()
        if prescription.stock_deducted:
            messages.info(request, "Dispense confirmed and stock updated.")

        return redirect('core:prescription_list')

    # Render confirmation page
    return render(request, 'prescription/dispense_prescription.html', {
        'prescription': prescription,
        'total_price': (prescription.clinic_medication.selling_price or 0) * prescription.quantity_prescribed
    })




@login_required
@clinic_selected_required
@role_required('ADMIN', 'DOCTOR', 'RECEPTIONIST')
def dispense_prescription(request, pk):
    """Dispense prescription, deduct stock, and add to billing."""
    prescription = get_object_or_404(Prescription, pk=pk)
    patient = prescription.patient

    if not prescription.clinic_medication:
        messages.error(request, "This prescription is not from clinic inventory and cannot be dispensed.")
        return redirect('core:patient_detail', pk=patient.patient_id)
    
    if prescription.stock_deducted:
        messages.info(request, "This prescription has already been dispensed.")
        return redirect('core:patient_list')


    if request.method == 'POST':
        # Deduct stock
        if prescription.deduct_stock():
            # Add billing
            price = (prescription.clinic_medication.selling_price or 0) * prescription.quantity_prescribed
            # patient.billing_total += price
            patient.save()

            log_action(
                request,
                'UPDATE',
                prescription,
                details=f"Dispensed prescription for {patient.full_name}: "
                        f"{prescription.clinic_medication.name} x{prescription.quantity_prescribed} (₦{price})"
            )

            messages.success(request, f"Prescription dispensed! Stock deducted, ₦{price} added to billing.")
        else:
            messages.error(request, "Insufficient stock to dispense this prescription.")

        return redirect('core:prescription_list')

    # Render confirmation page
    return render(request, 'prescription/dispense_prescription.html', {
    'prescription': prescription,
    'total_price': prescription.clinic_medication.selling_price * prescription.quantity_prescribed
})







@login_required
@clinic_selected_required
@role_required('ADMIN', 'DOCTOR', 'RECEPTIONIST')
def bulk_dispense(request):
    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected_prescriptions')
        if not selected_ids:
            messages.error(request, "No prescriptions selected.")
            return redirect(request.META.get('HTTP_REFERER'))

        prescriptions = Prescription.objects.filter(
            id__in=selected_ids, stock_deducted=False
        )
        
        if not prescriptions.exists():
            messages.info(request, "Selected prescriptions are already dispensed or invalid.")
            return redirect(request.META.get('HTTP_REFERER'))

        # Ensure all prescriptions are for the same patient and appointment
        patient_ids = set(p.patient_id for p in prescriptions)
        appointment_ids = set(
            p.appointment_id for p in prescriptions if hasattr(p, 'appointment')
        )

        if len(patient_ids) > 1 or len(appointment_ids) > 1:
            messages.error(
                request,
                "All selected prescriptions must belong to the same patient and appointment."
            )
            return redirect(request.META.get('HTTP_REFERER'))

        patient = prescriptions.first().patient
        clinic = prescriptions.first().clinic
        appointment = getattr(prescriptions.first(), 'appointment', None)

        total_amount = 0
        description_lines = []

        for pres in prescriptions:
            if pres.deduct_stock(bulk=True):  # 🚀 skip individual billing
                price = (pres.clinic_medication.selling_price or 0) * pres.quantity_prescribed
                total_amount += price
                description_lines.append(f"{pres.medication_name} x{pres.quantity_prescribed}")
            else:
                messages.warning(request, f"Insufficient stock for {pres.medication_name}. Skipped.")

        # Create single billing record
        if total_amount > 0:
            Billing.objects.create(
                patient=patient,
                clinic=clinic,
                appointment=appointment,
                amount=total_amount,
                service_date=timezone.now().date(),
                due_date=timezone.now().date(),
                description="; ".join(description_lines),
                created_by=request.user,
            )

            messages.success(request, f"Bulk dispense completed! ₦{total_amount} added to billing.")

        return redirect('core:prescription_list')


    else:
        messages.error(request, "Invalid request method.")
        return redirect(request.META.get('HTTP_REFERER'))






@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def low_stock_report(request):
    """Report of medications with low or no stock"""
    clinic_id = request.session.get('clinic_id')
    clinic = get_object_or_404(Clinic, id=clinic_id)
    
    # Get out of stock medications
    out_of_stock = ClinicMedication.objects.filter(
        clinic=clinic,
        quantity_in_stock=0,
        status='ACTIVE'
    ).order_by('name')
    
    # Get low stock medications (above 0 but below minimum)
    low_stock = ClinicMedication.objects.filter(
        clinic=clinic,
        quantity_in_stock__lte=F('minimum_stock_level'),
        quantity_in_stock__gt=0,
        status='ACTIVE'
    ).order_by('quantity_in_stock')
    
    # Get total medications count
    total_medications = ClinicMedication.objects.filter(clinic=clinic, status='ACTIVE').count()
    
    # Calculate well stocked count
    well_stocked_count = ClinicMedication.objects.filter(
        clinic=clinic,
        quantity_in_stock__gt=F('minimum_stock_level'),
        status='ACTIVE'
    ).count()
    
    context = {
        'clinic': clinic,
        'out_of_stock': out_of_stock,
        'low_stock': low_stock,
        'total_medications': total_medications,
        'well_stocked_count': well_stocked_count,
    }
    
    return render(request, 'inventory/low_stock_report.html', context)




@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def medication_detail(request, pk):
    """Detailed view of a medication with stock history"""
    clinic_id = request.session.get('clinic_id')
    medication = get_object_or_404(ClinicMedication, pk=pk, clinic_id=clinic_id)
    
    # Get recent stock movements
    recent_movements = medication.stock_movements.all().order_by('-created_at')[:20]
    
    # Get prescriptions using this medication
    recent_prescriptions = medication.prescriptions.filter(
        is_active=True
    ).order_by('-date_prescribed')[:10]
    
    context = {
        'medication': medication,
        'recent_movements': recent_movements,
        'recent_prescriptions': recent_prescriptions,
    }
    
    return render(request, 'inventory/medication_detail.html', context)


@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def expiring_soon_report(request):
    """Report of medications expiring soon"""
    clinic_id = request.session.get('clinic_id')
    clinic = get_object_or_404(Clinic, id=clinic_id)
    
    # Get medications expiring within 30 days
    today = timezone.now().date()
    thirty_days_later = today + timedelta(days=30)
    
    expiring_soon = ClinicMedication.objects.filter(
        clinic=clinic,
        expiry_date__lte=thirty_days_later,
        expiry_date__gte=today,
        status='ACTIVE'
    ).order_by('expiry_date')
    
    # Calculate days until expiry for each medication
    for medication in expiring_soon:
        medication.days_until_expiry = (medication.expiry_date - today).days
    
    context = {
        'clinic': clinic,
        'expiring_medications': expiring_soon,
        'today': today,
    }
    
    return render(request, 'inventory/expiring_soon_report.html', context)




from django.http import HttpResponse
import os
from django.conf import settings

def download_stock_template(request):
    # Path to your template file
    file_path = os.path.join(settings.BASE_DIR, 'inventory', 'static', 'doc', 'stock_template.csv')
    
    if os.path.exists(file_path):
        with open(file_path, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type="text/csv")
            response['Content-Disposition'] = 'inline; filename=' + os.path.basename(file_path)
            return response
    else:
        # Create a default template if it doesn't exist
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="stock_template.csv"'
        
     
        # Write CSV headers
        response.write("name,strength,quantity,cost_price,selling_price,expiry_date\n")
        
        # Write a sample row
        response.write("Paracetamol,500mg,100,50.00,75.00,2025-12-31\n")
        
        return response


# ---------- API ENDPOINTS ----------

@login_required
def medication_search_api(request):
    """API endpoint for searching medications (for AJAX)"""
    clinic_id = request.session.get('clinic_id')
    query = request.GET.get('q', '')
    
    if not clinic_id or not query:
        return JsonResponse({'results': []})
    
    medications = ClinicMedication.objects.filter(
        clinic_id=clinic_id,
        name__icontains=query,
        status='ACTIVE'
    )[:10]
    
    results = []
    for med in medications:
        stock_status = ""
        if med.is_out_of_stock:
            stock_status = " (OUT OF STOCK)"
        elif med.is_low_stock:
            stock_status = f" (LOW: {med.quantity_in_stock})"
        
        results.append({
            'id': med.id,
            'name': med.display_name + stock_status,
            'stock': med.quantity_in_stock,
            'is_out_of_stock': med.is_out_of_stock,
            'is_low_stock': med.is_low_stock
        })
    
    return JsonResponse({'results': results})


@login_required
def check_medication_stock(request, pk):
    """API to check current stock of a medication"""
    clinic_id = request.session.get('clinic_id')
    medication = get_object_or_404(ClinicMedication, pk=pk, clinic_id=clinic_id)
    
    return JsonResponse({
        'stock': medication.quantity_in_stock,
        'minimum_level': medication.minimum_stock_level,
        'is_out_of_stock': medication.is_out_of_stock,
        'is_low_stock': medication.is_low_stock,
        'stock_status': medication.stock_status
    })


# ---------- CATEGORY MANAGEMENT ----------

# @login_required
# @clinic_selected_required
# @role_required('ADMIN')
# def manage_categories(request):
#     """Manage medication categories"""
#     categories = MedicationCategory.objects.all().order_by('name')
    
#     if request.method == 'POST':
#         form = MedicationCategoryForm(request.POST)
#         if form.is_valid():
#             category = form.save()
#             messages.success(request, f"Category '{category.name}' created successfully!")
#             return redirect('core:prescription_menu')
#     else:
#         form = MedicationCategoryForm()
    
#     return render(request, 'inventory/manage_categories.html', {
#         'categories': categories,
#         'form': form
#     })


# Replace your existing manage_categories view with this fixed version:

@login_required
@clinic_selected_required
@role_required('ADMIN')
def manage_categories(request):
    """Manage medication categories for the current clinic"""
    clinic_id = request.session.get('clinic_id')
    clinic = get_object_or_404(Clinic, id=clinic_id)
    
    # Filter categories by clinic
    categories = MedicationCategory.objects.filter(clinic=clinic).order_by('name')
    
    if request.method == 'POST':
        form = MedicationCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.clinic = clinic  # Associate with current clinic
            category.save()
            
            log_action(
                request,
                'CREATE',
                category,
                details=f"Created medication category: {category.name}"
            )
            
            messages.success(request, f"Category '{category.name}' created successfully!")
            return redirect('core:manage_categories')
    else:
        form = MedicationCategoryForm()
    
    return render(request, 'inventory/manage_categories.html', {
        'categories': categories,
        'form': form,
        'clinic': clinic
    })


@login_required
@clinic_selected_required
@role_required('ADMIN')
def delete_medication(request, pk):
    """Delete a medication from inventory"""
    clinic_id = request.session.get('clinic_id')
    medication = get_object_or_404(ClinicMedication, pk=pk, clinic_id=clinic_id)
    
    if request.method == 'POST':
        # Check if medication has active prescriptions
        active_prescriptions = medication.prescriptions.filter(is_active=True).count()
        if active_prescriptions > 0:
            messages.error(request, 
                f"Cannot delete medication with {active_prescriptions} active prescriptions. "
                "Deactivate prescriptions first or set medication status to inactive."
            )
            return redirect('core:medication_list')
        
        medication_name = medication.display_name
        
        log_action(
            request,
            'DELETE',
            medication,
            details=f"Deleted medication: {medication_name}"
        )
        
        medication.delete()
        messages.success(request, f"Medication '{medication_name}' deleted successfully!")
        return redirect('core:medication_list')
    
    return render(request, 'inventory/confirm_delete_medication.html', {
        'medication': medication
    })
    
    
    
    


@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def service_list(request):
    clinic_id = request.session.get('clinic_id')
    services = ServicePriceList.objects.filter(clinic_id=clinic_id).order_by('name')
    return render(request, 'billing/service_list.html', {
        'services': services,
        'clinic': Clinic.objects.get(id=clinic_id)
    })

@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def add_service(request):
    clinic_id = request.session.get('clinic_id')
    
    if request.method == 'POST':
        form = ServicePriceListForm(request.POST)
        if form.is_valid():
            service = form.save(commit=False)
            service.clinic_id = clinic_id
            service.save()
            messages.success(request, f"Service '{service.name}' added successfully!")
            return redirect('core:service_list')
    else:
        form = ServicePriceListForm()
    
    return render(request, 'billing/service_form.html', {
        'form': form,
        'title': 'Add New Service'
    })

@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def edit_service(request, pk):
    clinic_id = request.session.get('clinic_id')
    service = get_object_or_404(ServicePriceList, pk=pk, clinic_id=clinic_id)
    
    if request.method == 'POST':
        form = ServicePriceListForm(request.POST, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, f"Service '{service.name}' updated successfully!")
            return redirect('core:service_list')
    else:
        form = ServicePriceListForm(instance=service)
    
    return render(request, 'billing/service_form.html', {
        'form': form,
        'title': 'Edit Service'
    })

@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def delete_service(request, pk):
    clinic_id = request.session.get('clinic_id')
    service = get_object_or_404(ServicePriceList, pk=pk, clinic_id=clinic_id)
    
    if request.method == 'POST':
        service_name = service.name
        service.delete()
        messages.success(request, f"Service '{service_name}' deleted successfully!")
        return redirect('core:service_list')
    
    return render(request, 'billing/confirm_delete.html', {
        'object': service,
        'title': 'Confirm Delete Service'
    })

@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def toggle_service_status(request, pk):
    clinic_id = request.session.get('clinic_id')
    service = get_object_or_404(ServicePriceList, pk=pk, clinic_id=clinic_id)
    service.is_active = not service.is_active
    service.save()
    
    action = "activated" if service.is_active else "deactivated"
    messages.success(request, f"Service '{service.name}' {action} successfully!")
    return redirect('core:service_list')






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


#--------------------------------------------------------------------------------------
#  Contact Forms
#--------------------------------------------------------------------------------------

from django.core.mail import send_mail, BadHeaderError
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib import messages
from django.template.loader import render_to_string
from django.utils.html import strip_tags




def contact_form(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        practice = request.POST.get('practice')
        message = request.POST.get('message')
        
        # Practice type mapping for better display
        practice_types = {
            'hospital': 'Hospital',
            'eye_clinic': 'Eye Clinic',
            'dental_clinic': 'Dental Clinic',
            'other': 'Other'
        }
        practice_display = practice_types.get(practice, 'Not specified')
        
        # Context data for email templates
        context = {
            'name': name,
            'email': email,
            'phone': phone,
            'practice': practice_display,
            'message': message,
            'website_url': 'https://durielmedic.pythonanywhere.com/',
            'company_name': 'Duriel Tech Solutions'
        }
        
        try:
            # 1. Send email to admin (HTML version)
            admin_subject = f"New Website Inquiry: {name} - {practice_display}"
            admin_html_message = render_to_string('emails/admin_contact_notification.html', context)
            admin_plain_message = strip_tags(admin_html_message)
            
            send_mail(
                admin_subject,
                admin_plain_message,
                settings.DEFAULT_FROM_EMAIL,
                ['suavedef@gmail.com'],  # Your admin email
                html_message=admin_html_message,
                fail_silently=False,
            )
            
            # 2. Send confirmation email to user (HTML version)
            user_subject = "Thank You for Contacting DurielMedic+"
            user_html_message = render_to_string('emails/user_confirmation.html', context)
            user_plain_message = strip_tags(user_html_message)
            
            send_mail(
                user_subject,
                user_plain_message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                html_message=user_html_message,
                fail_silently=False,
            )
            
            messages.success(request, 'Your message has been sent successfully! We will contact you soon.')
            return redirect('core:home')

        except BadHeaderError:
            messages.error(request, 'Invalid header found.')
            return redirect('core:home')
        except Exception as e:
            messages.error(request, 'There was an error sending your message. Please try again later.')
            # Log the error for debugging
            print(f"Email error: {str(e)}")
            return redirect('core:home')

    return redirect('core:home')



# Subscriptions and Payments

def select_plan(request):
    plans = [
        {'name': 'Monthly', 'price': 15000, 'type': 'MONTHLY'},
        {'name': 'Yearly', 'price': 150000, 'type': 'YEARLY'},
    ]
    return render(request, 'registration/select_plan.html', {'plans': plans})



# def register_facility(request, plan_type):
#     price_map = {'MONTHLY': 15000, 'YEARLY': 150000}
#     if request.method == 'POST':
#         form = FacilityRegistrationForm(request.POST)
#         if form.is_valid():
#             request.session['registration_data'] = form.cleaned_data
#             return redirect('core:paystack_payment')
#     else:
#         form = FacilityRegistrationForm(initial={
#             'clinic_type': '',  # You can let user select or enter clinic type/name
#             'amount': price_map.get(plan_type, 15000)
#         })
#     return render(request, 'registration/register_facility.html', {'form': form, 'plan_type': plan_type})

def register_facility(request, plan_type):
    price_map = {'MONTHLY': 15000, 'YEARLY': 150000}
    if request.method == 'POST':
        form = FacilityRegistrationForm(request.POST)
        if form.is_valid():
            # Store valid form data + plan type in session
            request.session['registration_data'] = form.cleaned_data
            request.session['plan_type'] = plan_type  # ✅ save plan type
            return redirect('core:paystack_payment')
    else:
        form = FacilityRegistrationForm(initial={
            'clinic_type': 'GENERAL',  # Default to GENERAL
            'amount': price_map.get(plan_type, 15000)
        })
    return render(request, 'registration/register_facility.html', {'form': form, 'plan_type': plan_type})




def paystack_payment(request):
    reg_data = request.session.get('registration_data')
    renewal = request.session.get('renewal')
    if not reg_data and not renewal:
        return redirect('core:select_plan')

    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    callback_url = request.build_absolute_uri(reverse('core:paystack_callback'))

    if reg_data:
        amount = int(reg_data['amount'])
        email = reg_data['email']
    else:
        plan_type = renewal['plan_type']
        clinic = get_object_or_404(Clinic, id=renewal['clinic_id'])
        email = clinic.email or (request.user.email if request.user.is_authenticated else None)
        amount = pay_amount_for_plan(plan_type)
        if not email:
            messages.error(request, "No email found to initialize payment.")
            return redirect('core:select_plan')

    payload = {
        "email": email,
        "amount": amount * 100,  # kobo
        "callback_url": callback_url
    }
    response = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    res_data = response.json()
    if res_data.get('status'):
        return redirect(res_data['data']['authorization_url'])
    messages.error(request, "Payment initialization failed. Try again.")
    return redirect('core:select_plan')


    
    
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import redirect
from django.contrib import messages
import requests
from .models import Clinic, CustomUser


# def paystack_callback(request):
#     reference = request.GET.get('reference')
#     if not reference:
#         messages.error(request, "Payment reference not found.")
#         return redirect('core:select_plan')

#     try:
#         # --- Verify transaction with Paystack ---
#         verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
#         headers = {
#             "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
#             "Content-Type": "application/json"
#         }
#         response = requests.get(verify_url, headers=headers)
#         res_data = response.json()

#         if res_data.get('status') and res_data['data']['status'] == 'success':
#             # --- Get registration data from session ---
#             data = request.session.get('registration_data')
#             plan_type = request.session.get('plan_type', 'MONTHLY')

#             if not data:
#                 messages.error(request, "Registration data not found. Please try registering again.")
#                 return redirect('core:select_plan')

#             # Required fields
#             required_fields = ['clinic_name', 'username', 'email', 'password']
#             for field in required_fields:
#                 if field not in data:
#                     messages.error(request, f"Missing required information: {field}. Please try registering again.")
#                     return redirect('core:select_plan')

#             # Validate clinic_type
#             VALID_CLINIC_TYPES = ['GENERAL', 'EYE', 'DENTAL']
#             clinic_type = data.get('clinic_type')
#             if not clinic_type or clinic_type not in VALID_CLINIC_TYPES:
#                 clinic_type = 'GENERAL'

#             try:
#                 # --- Create or get Clinic ---
#                 clinic, created = Clinic.objects.get_or_create(
#                     name=data['clinic_name'],
#                     defaults={
#                         'clinic_type': clinic_type,
#                         'address': data.get('clinic_address', ''),
#                         'phone': data.get('clinic_phone', ''),
#                         'email': data.get('clinic_email', '')
#                     }
#                 )

#                 # --- Create Admin User ---
#                 user = CustomUser.objects.create_user(
#                     username=data['username'],
#                     email=data['email'],
#                     password=data['password'],
#                     first_name=data.get('first_name', ''),
#                     last_name=data.get('last_name', ''),
#                     is_active=True,
#                     role='ADMIN'
#                 )
#                 user.title = data.get('title', '')
#                 user.phone = data.get('phone', '')  # ✅ correct field
#                 user.save()

#                 # Link user to clinic
#                 user.clinic.add(clinic)

#                 # --- Send activation email ---
#                 try:
#                     send_mail(
#                         "New Clinic Activation",
#                         f"New clinic '{clinic.name}' activated by {user.username}. Plan: {plan_type}",
#                         settings.DEFAULT_FROM_EMAIL,
#                         ['suavedef@gmail.com'],
#                         fail_silently=True
#                     )
#                 except Exception as e:
#                     print(f"Email sending failed: {str(e)}")  # Log but don’t break

#                 # --- Clear session safely ---
#                 request.session.pop('registration_data', None)
#                 request.session.pop('plan_type', None)

#                 messages.success(request, "Payment successful! Your account has been activated.")
#                 return redirect('core:login')

#             except Exception as e:
#                 messages.error(request, f"Error creating account: {str(e)}. Please contact support.")
#                 return redirect('core:select_plan')

#         else:
#             payment_message = res_data.get('message', 'Unknown error')
#             plan_type = request.session.get('plan_type', 'MONTHLY')
#             messages.error(request, f"Payment verification failed: {payment_message}")
#             return redirect('core:register_facility', plan_type=plan_type)

#     except Exception as e:
#         messages.error(request, f"An error occurred during payment verification: {str(e)}")
#         return redirect('core:select_plan')


def paystack_callback(request):
    # Handle TRIAL flow without Paystack (no reference needed)
    if request.session.get('plan_type') == 'TRIAL' and request.session.get('registration_data'):
        data = request.session.get('registration_data')

        required_fields = ['clinic_name', 'username', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                messages.error(request, f"Missing required information: {field}.")
                return redirect('core:select_plan')

        VALID_CLINIC_TYPES = ['GENERAL', 'EYE', 'DENTAL']
        clinic_type = data.get('clinic_type') if data.get('clinic_type') in VALID_CLINIC_TYPES else 'GENERAL'

        try:
            with transaction.atomic():
                clinic = Clinic.objects.create(
                    name=data['clinic_name'],
                    clinic_type=clinic_type,
                    address=data.get('clinic_address', ''),
                    phone=data.get('clinic_phone', ''),
                    email=data.get('clinic_email', '') or data['email']
                )
                # Start TRIAL immediately (models.set_subscription should set 7 days)
                clinic.set_subscription('TRIAL')

                user = CustomUser.objects.create_user(
                    username=data['username'],
                    email=data['email'],
                    password=data['password'],
                    first_name=data.get('first_name', ''),
                    last_name=data.get('last_name', ''),
                    is_active=True,
                    role='ADMIN'
                )
                user.title = data.get('title', '')
                user.phone = data.get('phone', '') or data.get('phone_number', '')
                user.primary_clinic = clinic
                user.save()
                user.clinic.add(clinic)

            # Notify
            try:
                send_mail(
                    "Trial Started - DurielMedic+",
                    f"Clinic '{clinic.name}' started a trial. Expires on {clinic.subscription_end_date}.",
                    settings.DEFAULT_FROM_EMAIL,
                    ['suavedef@gmail.com'],
                    fail_silently=True
                )
                if clinic.email:
                    send_mail(
                        "Welcome to DurielMedic+ (Trial)",
                        f"Your clinic '{clinic.name}' trial is active. It expires on {clinic.subscription_end_date}.",
                        settings.DEFAULT_FROM_EMAIL,
                        [clinic.email],
                        fail_silently=True
                    )
            except Exception:
                pass

            # Cleanup
            request.session.pop('registration_data', None)
            request.session.pop('plan_type', None)

            messages.success(request, f"Trial started. Expires on {clinic.subscription_end_date}.")
            return redirect('core:login')

        except Exception as e:
            messages.error(request, f"Could not start trial: {e}")
            return redirect('core:select_plan')

    # ----- Paid flows (require Paystack verification) -----
    reference = request.GET.get('reference')
    if not reference:
        messages.error(request, "Payment reference not found.")
        return redirect('core:select_plan')

    try:
        verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        response = requests.get(verify_url, headers=headers)
        res_data = response.json()

        if not (res_data.get('status') and res_data['data']['status'] == 'success'):
            payment_message = res_data.get('message', 'Unknown error')
            messages.error(request, f"Payment verification failed: {payment_message}")
            return redirect('core:select_plan')

        # Renewal flow (existing clinic)
        if request.session.get('renewal'):
            renewal = request.session.pop('renewal')
            plan_type = renewal['plan_type']
            clinic = get_object_or_404(Clinic, id=renewal['clinic_id'])
            clinic.set_subscription(plan_type)
            try:
                send_mail(
                    "Subscription Renewed",
                    f"{clinic.name} has renewed {plan_type}. Expires on {clinic.subscription_end_date}.",
                    settings.DEFAULT_FROM_EMAIL,
                    [clinic.email, 'suavedef@gmail.com'],
                    fail_silently=True
                )
            except Exception:
                pass
            messages.success(request, "Subscription renewed successfully.")
            return redirect('core:admin_dashboard')

        # Registration flow (new clinic + admin)
        data = request.session.get('registration_data')
        plan_type = request.session.get('plan_type', 'MONTHLY')
        if not data:
            messages.error(request, "Registration data not found. Please try again.")
            return redirect('core:select_plan')

        required_fields = ['clinic_name', 'username', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                messages.error(request, f"Missing required information: {field}.")
                return redirect('core:select_plan')

        VALID_CLINIC_TYPES = ['GENERAL', 'EYE', 'DENTAL']
        clinic_type = data.get('clinic_type')
        if clinic_type not in VALID_CLINIC_TYPES:
            clinic_type = 'GENERAL'

        with transaction.atomic():
            clinic = Clinic.objects.create(
                name=data['clinic_name'],
                clinic_type=clinic_type,
                address=data.get('clinic_address', ''),
                phone=data.get('clinic_phone', ''),
                email=data.get('clinic_email', '') or data['email']
            )
            clinic.set_subscription(plan_type)

            user = CustomUser.objects.create_user(
                username=data['username'],
                email=data['email'],
                password=data['password'],
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
                is_active=True,
                role='ADMIN'
            )
            user.title = data.get('title', '')
            user.phone = data.get('phone', '') or data.get('phone_number', '')
            user.primary_clinic = clinic
            user.save()
            user.clinic.add(clinic)

        try:
            send_mail(
                "New Clinic Activated",
                f"Clinic '{clinic.name}' activated by {user.username}. Plan: {plan_type}. Expires on {clinic.subscription_end_date}.",
                settings.DEFAULT_FROM_EMAIL,
                ['suavedef@gmail.com'],
                fail_silently=True
            )
            if clinic.email:
                send_mail(
                    "Welcome to DurielMedic+",
                    f"Your clinic '{clinic.name}' has been activated. Plan: {plan_type}. Expires on {clinic.subscription_end_date}.",
                    settings.DEFAULT_FROM_EMAIL,
                    [clinic.email],
                    fail_silently=True
                )
        except Exception:
            pass

        # Cleanup
        request.session.pop('registration_data', None)
        request.session.pop('plan_type', None)

        messages.success(request, "Payment successful! Your account is activated.")
        return redirect('core:login')

    except Exception as e:
        messages.error(request, f"An error occurred during payment verification: {str(e)}")
        return redirect('core:select_plan')

    
    
    
    
def pay_amount_for_plan(plan_type: str) -> int:
    return 15000 if plan_type == 'MONTHLY' else 150000

@login_required
def start_renewal(request, clinic_id, plan_type):
    if plan_type not in ('MONTHLY', 'YEARLY'):
        messages.error(request, "Invalid plan.")
        return redirect('core:select_plan')

    clinic = get_object_or_404(Clinic, id=clinic_id)
    # Only superuser or ADMIN within the clinic can renew
    if not (request.user.is_superuser or (clinic in request.user.clinic.all() and getattr(request.user, 'role', '') == 'ADMIN')):
        messages.error(request, "You do not have permission to renew this clinic.")
        return redirect('core:select_clinic')

    request.session['renewal'] = {'clinic_id': clinic.id, 'plan_type': plan_type}
    request.session['plan_type'] = plan_type
    return redirect('core:paystack_payment')

# Sending real time Notification using websocket

from core.models import Notification
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def notify_user(user, message, link=None, clinic=None, app_name=None):
    # Save to DB using your Notification model
    notif = Notification.objects.create(
        user=user,
        clinic=clinic,
        message=message,
        link=link,
        app_name=app_name
    )
    # Send via WebSocket
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{user.id}",
        {
            "type": "send_notification",
            "notification": {
                "id": notif.id,
                "message": notif.message,
                "link": notif.link,
                "created_at": notif.created_at.strftime("%Y-%m-%d %H:%M"),
                "is_read": notif.is_read,
                "app_name": notif.app_name,
                "clinic": notif.clinic.name if notif.clinic else "",
            }
        }
    )