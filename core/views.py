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
from django.http import HttpResponse
import csv

from .models import CustomUser, Patient, Billing, Clinic, Payment
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
from DurielMedicApp.models import Appointment, MedicalRecord, Prescription  








# ---------- Role Checks ----------
def staff_check(user):
    return user.is_authenticated and user.role in ['ADMIN', 'DOCTOR', 'NURSE', 'OPTOMETRIST', 'PHYSIOTHERAPIST', 'RECEPTIONIST']

def admin_check(user):
    return user.is_authenticated and user.role == 'ADMIN'


# ---------- HOME ----------
# @login_required
# def home_view(request):
#     return redirect('DurielMedicApp:dashboard')


def home(request):
    return render(request, 'core/login.html')


# ---------- USER ROLE MANAGEMENT ----------
@login_required
def manage_user_roles(request):
    users = CustomUser.objects.all()
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


@login_required
def edit_user_role(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)

    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'User details updated successfully.')
            return redirect('core:manage_roles')
    else:
        form = UserEditForm(instance=user)
        form.fields['clinic'].queryset = Clinic.objects.all()

    return render(request, 'administration/edit_user_role.html', {
        'form': form,
        'user_obj': user,
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
        queryset = super().get_queryset()
        search_query = self.request.GET.get('search', '')
        if search_query:
            queryset = queryset.filter(
                full_name__icontains=search_query
            )
        return queryset.order_by('-created_at')


class PatientCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Patient
    form_class = PatientForm
    template_name = 'patients/add_patient.html'
    success_url = reverse_lazy('core:patient_list')

    def test_func(self):
        return self.request.user.role in ['ADMIN', 'DOCTOR', 'RECEPTIONIST', 'NURSE']

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.clinic = self.request.user.primary_clinic
        messages.success(self.request, 'Patient added successfully!')
        return super().form_valid(form)


class PatientUpdateView(UpdateView):
    model = Patient
    fields = ['full_name', 'date_of_birth', 'gender', 'contact', 'address']
    template_name = 'patients/edit_patient.html'
    success_url = reverse_lazy('core:patient_list')


class PatientDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Patient
    template_name = 'patients/patient_detail.html'
    context_object_name = 'patient'
    
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role in ['ADMIN', 'DOCTOR', 'NURSE', 'RECEPTIONIST']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        patient = self.get_object()
        
        # Get the latest vitals if available
        appointment = patient.appointments.filter(status='SCHEDULED').first()
        if appointment:
            context['vitals'] = getattr(appointment, 'vitals', None)
        
        # Add all required context data
        context['medical_records'] = MedicalRecord.objects.filter(patient=patient).order_by('-created_at')
        context['appointments'] = Appointment.objects.filter(patient=patient).order_by('-date', '-start_time')
        context['prescriptions'] = Prescription.objects.filter(patient=patient, is_active=True).order_by('-date_prescribed')
        context['deactivated_prescriptions'] = Prescription.objects.filter(patient=patient, is_active=False).order_by('-date_prescribed')
        context['bills'] = Billing.objects.filter(patient=patient).order_by('-service_date')
        
        return context


class PatientDeleteView(DeleteView):
    model = Patient
    template_name = 'patients/confirm_delete.html'
    success_url = reverse_lazy('core:patient_list')


# ---------- STAFF ----------
@login_required
@user_passes_test(admin_check)
def staff_list(request):
    staff = CustomUser.objects.filter(is_staff=True).exclude(role='ADMIN')
    return render(request, 'staff/staff_list.html', {'staff': staff})


class StaffCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = CustomUser
    form_class = CustomUserCreationForm
    template_name = 'staff/staff_form.html'
    success_url = reverse_lazy('staff_list')

    def test_func(self):
        return admin_check(self.request.user)

    def form_valid(self, form):
        form.instance.is_staff = True
        messages.success(self.request, 'Staff member added successfully!')
        return super().form_valid(form)


# ---------- REPORTS ----------
# @login_required
# @clinic_selected_required
# @user_passes_test(admin_check)
# def generate_report(request):
#     end_date = timezone.now()
#     start_date = end_date - timedelta(days=30)

#     if request.method == 'POST':
#         start_date_str = request.POST.get('start_date')
#         end_date_str = request.POST.get('end_date')
#         report_type = request.POST.get('report_type')

#         if start_date_str and end_date_str:
#             start_date = timezone.make_aware(datetime.strptime(start_date_str, '%Y-%m-%d'))
#             end_date = timezone.make_aware(datetime.strptime(end_date_str, '%Y-%m-%d'))

#         if report_type == 'patients':
#             return generate_patient_report(start_date, end_date)
#         elif report_type == 'financial':
#             return generate_financial_report(start_date, end_date)

#     return render(request, 'reports/generate_report.html', {
#         'start_date': start_date.date(),
#         'end_date': end_date.date(),
#     })


# def generate_patient_report(start_date, end_date):
#     patients = Patient.objects.filter(created_at__range=[start_date, end_date])
#     response = HttpResponse(content_type='text/csv')
#     response['Content-Disposition'] = f'attachment; filename="patients_{start_date.date()}_to_{end_date.date()}.csv"'
#     writer = csv.writer(response)
#     writer.writerow(['Patient ID', 'Name', 'Gender', 'DOB', 'Contact', 'Created'])
#     for patient in patients:
#         writer.writerow([
#             patient.patient_id,
#             patient.full_name,
#             patient.get_gender_display(),
#             patient.date_of_birth,
#             patient.contact,
#             patient.created_at
#         ])
#     return response


# def generate_financial_report(start_date, end_date):
#     bills = Billing.objects.filter(service_date__range=[start_date.date(), end_date.date()])
#     response = HttpResponse(content_type='text/csv')
#     response['Content-Disposition'] = f'attachment; filename="financial_{start_date.date()}_to_{end_date.date()}.csv"'
#     writer = csv.writer(response)
#     writer.writerow(['Date', 'Patient', 'Amount', 'Paid', 'Balance', 'Status', 'Description'])
#     for bill in bills:
#         writer.writerow([
#             bill.service_date,
#             bill.patient.full_name if bill.patient else '',
#             bill.amount,
#             bill.paid_amount,
#             bill.amount - bill.paid_amount,
#             bill.get_status_display(),
#             bill.description
#         ])
#     return response


# ---------- BILLING ----------
# @login_required
# @clinic_selected_required
# @role_required('ADMIN', 'RECEPTIONIST')
# def billing_list(request):
#     bills = Billing.objects.select_related('patient').order_by('-service_date')
#     context = {
#         'bills': bills,
#         'total_amount': bills.aggregate(total=Sum('amount'))['total'] or 0,
#         'total_paid': bills.aggregate(total=Sum('paid_amount'))['total'] or 0,
#     }
#     return render(request, 'billing/billing_list.html', context)

@login_required
@clinic_selected_required
@role_required('ADMIN', 'RECEPTIONIST')
def billing_list(request):
    bills = Billing.objects.select_related('patient').order_by('-service_date')
    
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
    patient = get_object_or_404(Patient, pk=patient_id) if patient_id else None
    patients_with_appointments = Patient.objects.all()

    # Get selected patient from GET parameters
    selected_patient_id = request.GET.get('patient')
    if selected_patient_id:
        try:
            patient = Patient.objects.get(patient_id=selected_patient_id)  # Changed to patient_id
        except Patient.DoesNotExist:
            pass

    if request.method == 'POST':
        form = BillingForm(request.POST)
        if form.is_valid():
            bill = form.save(commit=False)
            bill.created_by = request.user
            
            clinic_id = request.session.get('clinic_id')
            if not clinic_id:
                messages.error(request, "No clinic selected.")
                return redirect('select_clinic')

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
            messages.success(request, "Bill created successfully!")
            return redirect('core:billing_list')
    else:
        form = BillingForm(initial={'service_date': date.today()})
        if patient:
            form.initial['patient'] = patient.patient_id  # Changed to patient_id

    # Get appointment
    appointment_id = request.GET.get('appointment_id')
    if appointment_id:
        appointment = Appointment.objects.filter(id=appointment_id).first()
    elif patient:
        appointment = Appointment.objects.filter(patient=patient).order_by('-date', '-start_time').first()
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
        bill.delete()
        messages.success(request, "Bill deleted successfully!")
        return redirect('core:billing_list')
    return render(request, 'billing/confirm_delete.html', {'bill': bill})



def logout_view(request):
    logout(request)
    return redirect('login')  # or 'core:login' if namespaced





def patient_search_api(request):
    query = request.GET.get('q', '')
    results = Patient.objects.filter(full_name__icontains=query)
    data = [{'id': p.id, 'name': p.full_name} for p in results]
    return JsonResponse({'results': data})




# @login_required
# def patient_search_api(request):
#     term = request.GET.get('q', '')
#     results = []

#     if term:
#         patients = Patient.objects.filter(full_name__icontains=term)[:10]
#         results = [
#             {
#                 'id': p.id,
#                 'full_name': p.full_name,
#                 'patient_id': p.patient_id
#             }
#             for p in patients
#         ]

#     return JsonResponse(results, safe=False)


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