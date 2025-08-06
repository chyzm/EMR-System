from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Q, Count
from datetime import date, timedelta
from .models import CustomUser, Patient, Appointment, Prescription, MedicalRecord, Billing, Notification
from .forms import (CustomUserCreationForm, PatientForm, AppointmentForm, 
                   PrescriptionForm, MedicalRecordForm, BillingForm)
from .decorators import role_required
from django.http import JsonResponse
# from .forms import RoleForm  
# from .forms import RoleUpdateForm
from .forms import UserCreationWithRoleForm, UserEditForm
from django.contrib.auth import logout
from .models import Clinic
from django.views.decorators.http import require_POST
from .forms import VitalsForm, AdmissionForm, FollowUpForm
from django.urls import reverse, reverse_lazy  
from .models import Admission, Notification, Patient
from django.utils import timezone
from datetime import date
from django.core.mail import send_mail
from django.conf import settings
from django.db.models.functions import Coalesce
from .models import Payment, NotificationRead










# Utility functions
def staff_check(user):
    return user.is_authenticated and user.role in ['ADMIN', 'DOCTOR', 'NURSE', 'OPTOMETRIST', 'PHYSIOTHERAPIST', 'RECEPTIONIST']

def admin_check(user):
    return user.is_authenticated and user.role == 'ADMIN'

def doctor_check(user):
    return user.is_authenticated and user.role == 'DOCTOR'

    
def home_view(request):
    if request.user.is_authenticated:
        return redirect('DurielMedicApp:dashboard')
    return redirect('login')




@login_required
def manage_user_roles(request):
    users = CustomUser.objects.all()
    # users = CustomUser.objects.exclude(id=request.user.id)  # Don't show the current user
    new_user_form = UserCreationWithRoleForm()
    new_user_form.fields['clinic'].queryset = Clinic.objects.all()
    role_forms = {user.id: UserEditForm(instance=user) for user in users}

    # Handle POST
    if request.method == 'POST':
        if 'create_user' in request.POST:
            new_user_form = UserCreationWithRoleForm(request.POST)
            if new_user_form.is_valid():
                new_user_form.save()
                return redirect('DurielMedicApp:manage_roles')
        elif 'update_role' in request.POST:
            user_id = request.POST.get('user_id')
            user = get_object_or_404(CustomUser, id=user_id)
            role_form = UserEditForm(request.POST, instance=user)
            if role_form.is_valid():
                role_form.save()
                return redirect('DurielMedicApp:manage_roles')


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
            return redirect('DurielMedicApp:manage_roles')
    else:
        form = UserEditForm(instance=user)
        form.fields['clinic'].queryset = Clinic.objects.all()

    return render(request, 'administration/edit_user_role.html', {
        'form': form,
        'user_obj': user,
    })

    




# Dashboard View
from django.utils import timezone

# @login_required
# @user_passes_test(staff_check, login_url='login')
# def dashboard(request):
#     today = date.today()
#     start_week = today - timedelta(days=today.weekday())
#     end_week = start_week + timedelta(days=6)
    
#     stats = {
#         'total_patients': Patient.objects.count(),
#         'today_appointments': Appointment.objects.filter(date=today).count(),
#         'week_appointments': Appointment.objects.filter(date__range=[start_week, end_week]).count(),
#         'pending_prescriptions': Prescription.objects.filter(is_active=True).count(),
#         'pending_bills': Billing.objects.filter(status='PENDING').count(),
#     }

#     user_appointments = Appointment.objects.filter(
#         start_time__gte=timezone.now() - timedelta(hours=24)
#     ).order_by('-start_time')[:5]

#     recent_patients = Patient.objects.order_by('-created_at')[:5]
#     notifications = Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')[:5]
    
#     context = {
#         'stats': stats,
#         'user_appointments': user_appointments,
#         'recent_patients': recent_patients,
#         'notifications': notifications,
#         'today': today,
#     }
    
#     return render(request, 'dashboard.html', context)


from django.db.models import Value, Sum, Count, DecimalField
from django.db.models.functions import Coalesce

@login_required
@user_passes_test(staff_check, login_url='login')
def dashboard(request):
    today = date.today()
    start_week = today - timedelta(days=today.weekday())
    end_week = start_week + timedelta(days=6)
    start_year = date(today.year, 1, 1)
    
    # Calculate financial statistics with proper output fields
    financial_stats = Billing.objects.filter(status='PENDING').aggregate(
        total_count=Count('id'),
        total_amount=Coalesce(
            Sum('amount', output_field=DecimalField()),
            Value(0, output_field=DecimalField())
        ),
        total_paid=Coalesce(
            Sum('paid_amount', output_field=DecimalField()),
            Value(0, output_field=DecimalField())
        )
    )
    
    stats = {
        # Patient statistics
        'total_patients': Patient.objects.count(),
        'new_patients_this_week': Patient.objects.filter(
            created_at__date__range=[start_week, today]
        ).count(),
        'new_patients_this_year': Patient.objects.filter(
            created_at__date__gte=start_year
        ).count(),
        
        # Appointment statistics
        'today_appointments': Appointment.objects.filter(date=today).count(),
        'completed_appointments_today': Appointment.objects.filter(
            date=today, status='COMPLETED'
        ).count(),
        'week_appointments': Appointment.objects.filter(
            date__range=[start_week, end_week]
        ).count(),
        
        # Prescription statistics
        'pending_prescriptions': Prescription.objects.filter(is_active=True).count(),
        'new_prescriptions_this_week': Prescription.objects.filter(
            date_prescribed__range=[start_week, today]
        ).count(),
        
        # Financial statistics
        'pending_bills': financial_stats['total_count'],
        'total_pending_amount': financial_stats['total_amount'],
        'outstanding_balance': financial_stats['total_amount'] - financial_stats['total_paid'],
        
        'pending_bills': Billing.objects.filter(status='PENDING').count(),
        'total_pending_amount': Billing.objects.filter(status='PENDING').aggregate(
            total=Sum('amount', output_field=DecimalField())
        )['total'] or 0,
        'outstanding_balance': Billing.objects.aggregate(
            total=Sum(F('amount') - F('paid_amount'), output_field=DecimalField())
        )['total'] or 0,
    }

    # Get ALL today's appointments for all staff users
    user_appointments = Appointment.objects.filter(
        date=today
    ).order_by('start_time')[:5]  # Show first 5 appointments of the day

    # Get recent patients
    recent_patients = Patient.objects.order_by('-created_at')[:5]
    
   

    # Get notifications not yet read by this user
    read_global_ids = NotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)

    notifications = Notification.objects.filter(
        Q(user=request.user, is_read=False) |
        Q(user__isnull=True)  # global
    ).exclude(id__in=read_global_ids).order_by('-created_at')[:5]

    
    context = {
        'stats': stats,
        'user_appointments': user_appointments,
        'recent_patients': recent_patients,
        'notifications': notifications,
        'today': today,
    }
    
    return render(request, 'dashboard.html', context)



# Patient Views
class PatientListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Patient
    template_name = 'patients/patient_list.html'
    context_object_name = 'patients'
    paginate_by = 10
    
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role in ['ADMIN', 'DOCTOR', 'NURSE', 'RECEPTIONIST']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        search_query = self.request.GET.get('search', '')
        
        if search_query:
            queryset = queryset.filter(
                Q(full_name__icontains=search_query) |
                Q(patient_id__icontains=search_query) |
                Q(contact__icontains=search_query)
            )
        
        return queryset.order_by('-created_at')

# class PatientDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
#     model = Patient
#     template_name = 'patients/patient_detail.html'
#     context_object_name = 'patient'
    
#     def test_func(self):
#         return self.request.user.is_authenticated and self.request.user.role in ['ADMIN', 'DOCTOR', 'NURSE', 'RECEPTIONIST']
    
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         patient = self.get_object()
#         context['medical_records'] = MedicalRecord.objects.filter(patient=patient).order_by('-created_at')
#         context['appointments'] = Appointment.objects.filter(patient=patient).order_by('-date', '-start_time')
#         context['prescriptions'] = Prescription.objects.filter(patient=patient, is_active=True).order_by('-date_prescribed')
#         context['deactivated_prescriptions'] = Prescription.objects.filter(patient=patient, is_active=False).order_by('-date_prescribed')
#         context['bills'] = Billing.objects.filter(patient=patient).order_by('-service_date')
#         return context



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
        
        context['medical_records'] = MedicalRecord.objects.filter(patient=patient).order_by('-created_at')
        context['appointments'] = Appointment.objects.filter(patient=patient).order_by('-date', '-start_time')
        context['prescriptions'] = Prescription.objects.filter(patient=patient, is_active=True).order_by('-date_prescribed')
        context['deactivated_prescriptions'] = Prescription.objects.filter(patient=patient, is_active=False).order_by('-date_prescribed')
        context['bills'] = Billing.objects.filter(patient=patient).order_by('-service_date')
        return context
    
    

class PatientCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Patient
    form_class = PatientForm
    template_name = 'patients/add_patient.html'
    success_url = reverse_lazy('DurielMedicApp:patient_list')
    
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role in ['ADMIN', 'DOCTOR', 'RECEPTIONIST', 'NURSE']
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.clinic = self.request.user.clinic  # Assuming user has a clinic attribute
        messages.success(self.request, 'Patient added successfully!')
        return super().form_valid(form)
    
    
    # @login_required
    # def patient_detail(request, pk):
    #     patient = get_object_or_404(Patient, patient_id=pk)
    #     medical_records = MedicalRecord.objects.filter(patient=patient).order_by('-created_at')
    #     appointments = Appointment.objects.filter(patient=patient).order_by('-date', '-start_time')
    #     prescriptions = Prescription.objects.filter(patient=patient, is_active=True).order_by('-date_prescribed')
        
    #     context = {
    #         'patient': patient,
    #         'medical_records': medical_records,
    #         'appointments': appointments,
    #         'prescriptions': prescriptions,
    #     }
        return render(request, 'patients/patient_detail.html', context)
    

class PatientDeleteView(DeleteView):
    model = Patient
    template_name = 'patients/confirm_delete.html'  # adjust template path as needed
    success_url = reverse_lazy('DurielMedicApp:patient_list')  # redirect after deletion
    
    
    


@login_required 
@role_required('NURSE', 'DOCTOR')
def record_vitals(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    appointment = patient.appointments.filter(status='SCHEDULED').order_by('-date', '-start_time').first()

    if not appointment:
        messages.error(request, "No active appointment found for this patient.")
        return redirect('DurielMedicApp:patient_detail', pk=patient_id)

    if request.method == 'POST':
        form = VitalsForm(request.POST)
        if form.is_valid():
            vitals = form.save(commit=False)
            vitals.appointment = appointment
            vitals.save()

            # Update patient status
            patient.status = 'VITALS_TAKEN'
            patient.save()

            messages.success(request, "Vitals recorded successfully!")
            return redirect('DurielMedicApp:patient_detail', pk=patient_id)
    else:
        form = VitalsForm(initial={'appointment': appointment})

    return render(request, 'vitals/record_vitals.html', {
        'form': form,
        'patient': patient,
        'appointment': appointment
    })

    

from django.contrib.auth import get_user_model
from django.urls import reverse

@login_required
@role_required('DOCTOR')
def begin_consultation(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    
    if patient.status != 'VITALS_TAKEN':
        messages.error(request, "Patient vitals must be taken before consultation")
        return redirect('DurielMedicApp:patient_detail', pk=patient_id)
    
    patient.status = 'IN_CONSULTATION'
    patient.save()

    # ✅ Send notification to all active users
    User = get_user_model()
    users = User.objects.filter(is_active=True)

    for user in users:
        Notification.objects.create(
            user=user,
            message=f"Consultation started for patient {patient.full_name}",
            link=reverse('DurielMedicApp:patient_detail', kwargs={'pk': patient_id})
        )

    messages.success(request, "Consultation started")
    return redirect('DurielMedicApp:patient_detail', pk=patient_id)


    
    
# @login_required
# @role_required('DOCTOR')
# def complete_consultation(request, patient_id):
#     patient = get_object_or_404(Patient, pk=patient_id)
    
#     if patient.status != 'IN_CONSULTATION':
#         messages.error(request, "Patient must be in consultation first")
#         return redirect('DurielMedicApp:patient_detail', pk=patient_id)
    
#     patient.status = 'CONSULTATION_COMPLETE'
#     patient.save()
    
#     messages.success(request, "Consultation completed successfully")
#     return redirect('DurielMedicApp:patient_detail', pk=patient_id)


from django.contrib.auth import get_user_model
from django.urls import reverse
from datetime import date, timedelta

@login_required
@role_required('DOCTOR')
def complete_consultation(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)

    if patient.status != 'IN_CONSULTATION':
        messages.error(request, "Patient must be in consultation first")
        return redirect('DurielMedicApp:patient_detail', pk=patient_id)

    patient.status = 'CONSULTATION_COMPLETE'
    patient.save()

    # ✅ Create the bill
    bill = Billing.objects.create(
        patient=patient,
        amount=5000,  # Replace with dynamic value if needed
        description=f"Consultation fee - {date.today()}",
        service_date=date.today(),
        due_date=date.today() + timedelta(days=14),
        created_by=request.user
    )

    # ✅ Send notification to all active users
    User = get_user_model()
    users = User.objects.filter(is_active=True)

    for user in users:
        Notification.objects.create(
            user=user,
            message=f"New bill created for {patient.full_name} - ₦{bill.amount:,.2f}",
            link=reverse('DurielMedicApp:view_bill', kwargs={'pk': bill.pk})
        )

    messages.success(request, "Consultation completed successfully. Consultation fee bill created.")
    return redirect('DurielMedicApp:patient_detail', pk=patient_id)





@login_required
@role_required('DOCTOR')
def schedule_follow_up(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    
    if patient.status not in ['IN_CONSULTATION', 'CONSULTATION_COMPLETE']:
        messages.error(request, "Patient must complete consultation first")
        return redirect('DurielMedicApp:patient_detail', pk=patient_id)
    
    if request.method == 'POST':
        form = FollowUpForm(request.POST)
        if form.is_valid():
            follow_up = form.save(commit=False)
            follow_up.patient = patient
            follow_up.created_by = request.user
            follow_up.save()
            
            patient.status = 'FOLLOW_UP'
            patient.save()
            
            messages.success(request, "Follow-up scheduled successfully!")
            return redirect('DurielMedicApp:patient_detail', pk=patient_id)
    else:
        form = FollowUpForm()
    
    return render(request, 'follow_up/schedule_follow_up.html', {
        'form': form,
        'patient': patient,
        'from_consultation': patient.status == 'IN_CONSULTATION'
    })
    
    
@login_required
def complete_follow_up(request, pk):
    follow_up = get_object_or_404(FollowUp, pk=pk)
    patient = follow_up.patient  # Get the patient from the follow-up
    
    if not follow_up.completed:
        follow_up.completed = True
        follow_up.save()
        
        # Update patient status if this was their last pending follow-up
        if not patient.follow_ups.filter(completed=False).exists():
            patient.status = 'FOLLOW_UP_COMPLETE'
            patient.save()
        
        messages.success(request, "Follow-up marked as complete.")
    else:
        messages.warning(request, "This follow-up was already completed.")
    
    return redirect('DurielMedicApp:patient_detail', pk=patient.pk)





from django.views.generic import ListView, DetailView, UpdateView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import FollowUp

class FollowUpListView(LoginRequiredMixin, ListView):
    model = FollowUp
    template_name = 'follow_up/followup_list.html'
    context_object_name = 'followups'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if not user.is_superuser:
            role = getattr(user, 'role', None)

            if role == 'DOCTOR':
                queryset = queryset.filter(created_by=user)
            elif role == 'NURSE':
                # Change this logic based on your actual nurse-followup link
                # For now, allow nurse to see all follow-ups
                queryset = queryset  # or .none() if nurses should not see any

        return queryset.order_by('scheduled_date', 'scheduled_time')


class FollowUpCreateView(LoginRequiredMixin, CreateView):
    model = FollowUp
    template_name = 'follow_up/schedule_follow_up.html'
    fields = ['patient', 'reason', 'scheduled_date', 'scheduled_time', 'notes']
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

class FollowUpUpdateView(LoginRequiredMixin, UpdateView):
    model = FollowUp
    template_name = 'followup_form.html'
    fields = ['reason', 'scheduled_date', 'scheduled_time', 'notes', 'completed']

    
    

@login_required
@role_required('DOCTOR', 'NURSE')
def admit_patient(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    
    # Allow admission from multiple states
    if patient.status not in ['VITALS_TAKEN', 'CONSULTATION_COMPLETE']:
        messages.error(request, "Patient must have vitals taken or consultation completed first")
        return redirect('DurielMedicApp:patient_detail', pk=patient_id)
    
    if request.method == 'POST':
        form = AdmissionForm(request.POST)
        if form.is_valid():
            admission = form.save(commit=False)
            admission.patient = patient
            admission.save()
            
            patient.status = 'ADMITTED'
            patient.save()
            
            messages.success(request, "Patient admitted successfully!")
            return redirect('DurielMedicApp:patient_detail', pk=patient_id)
    else:
        form = AdmissionForm(initial={'patient': patient})
    
    return render(request, 'admission/admit_patient.html', {
        'form': form,
        'patient': patient,
        'from_consultation': patient.status == 'CONSULTATION_COMPLETE'
    })
    
    
    

@login_required
@role_required('DOCTOR')
def mark_ready_for_doctor(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    
    if patient.status != 'ADMITTED':
        messages.error(request, "Patient must be admitted before seeing doctor")
        return redirect('DurielMedicApp:patient_detail', pk=patient_id)
    
    patient.status = 'SEEN_BY_DOCTOR'
    patient.save()
    
    messages.success(request, "Patient is now with doctor")
    return redirect('DurielMedicApp:patient_detail', pk=patient_id)



@login_required
@role_required('DOCTOR', 'NURSE')
def discharge_patient(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    admission = Admission.objects.filter(patient=patient, discharged=False).first()
    
    if not admission:
        messages.error(request, "No active admission found for this patient")
        return redirect('DurielMedicApp:patient_detail', pk=patient_id)
    
    admission.discharged = True
    admission.save()
    
    # Reset patient status
    patient.status = 'REGISTERED'
    patient.save()
    
    messages.success(request, "Patient discharged successfully")
    return redirect('DurielMedicApp:patient_detail', pk=patient_id)




@login_required
def add_prescription(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id)

    if request.method == 'POST':
        medication = request.POST.get('medication')
        dosage = request.POST.get('dosage')
        instructions = request.POST.get('instructions')

        # Validation (optional)
        if not medication or not dosage:
            messages.error(request, "Please fill in all required fields.")
        else:
            Prescription.objects.create(
                patient=patient,
                medication=medication,
                dosage=dosage,
                instructions=instructions,
                prescribed_by=request.user  
            )
            messages.success(request, "Prescription saved successfully.")
            return redirect('DurielMedicApp:patient_detail', pk=patient.patient_id)
        Notification.objects.create(
            user=prescription.patient.created_by,
            message=f"New prescription for {prescription.patient.full_name}",
            link=reverse('DurielMedicApp:patient_detail', kwargs={'pk': prescription.patient.pk})
        )

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
        return redirect('DurielMedicApp:patient_detail', pk=patient.patient_id)

    return render(request, 'prescription/edit_prescription.html', {'prescription': prescription, 'patient': patient})

@login_required
def prescription_list(request):
    query = request.GET.get('q', '')
    prescriptions = Prescription.objects.select_related('patient', 'prescribed_by')

    if query:
        prescriptions = prescriptions.filter(
            Q(patient__first_name__icontains=query) |
            Q(patient__last_name__icontains=query) |
            Q(doctor__first_name__icontains=query) |
            Q(doctor__last_name__icontains=query) |
            Q(date_prescribed__icontains=query)
        )

    context = {
        'prescriptions': prescriptions.order_by('-date_prescribed'),
        'query': query,
    }
    return render(request, 'prescription/prescription_list.html', context)


@login_required
def deactivate_prescription(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk)
    patient = prescription.patient

    if request.method == 'POST':
        prescription.is_active = False
        prescription.save()
        return redirect('DurielMedicApp:patient_detail', pk=patient.patient_id)

    return render(request, 'prescription/deactivate_prescription.html', {
        'prescription': prescription,
        'patient': patient
    })

    

class PatientUpdateView(UpdateView):
    model = Patient
    fields = ['full_name', 'date_of_birth', 'gender', 'contact', 'address']
    template_name = 'patients/edit_patient.html'
    success_url = reverse_lazy('DurielMedicApp:patient_list')


# Appointment Views
class AppointmentListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Appointment
    template_name = 'appointments/appointment_list.html'
    context_object_name = 'appointments'
    paginate_by = 10
    
    def test_func(self):
        return self.request.user.is_authenticated and staff_check(self.request.user)
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by date if provided
        date_filter = self.request.GET.get('date', '')
        if date_filter:
            queryset = queryset.filter(date=date_filter)
        
        # For non-admin staff, only show their appointments or patients they created
        if not self.request.user.role == 'ADMIN':
            queryset = queryset.filter(
                Q(provider=self.request.user) | 
                Q(patient__created_by=self.request.user)
            )
        
        return queryset.order_by('date', 'start_time')

class AppointmentCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Appointment
    form_class = AppointmentForm
    template_name = 'appointments/appointment_form.html'
    success_url = reverse_lazy('appointment_list')
    
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role in ['ADMIN', 'DOCTOR', 'RECEPTIONIST']
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['initial'] = {'provider': self.request.user}
        return kwargs
    
    def form_valid(self, form):
        
        form.instance.provider = self.request.user  # 👈 THIS is crucial
        print("Saving appointment for:", form.cleaned_data.get('patient'))

        appointment = form.save(commit=False)
        appointment.save()

        messages.success(self.request, 'Appointment scheduled successfully!')
        return redirect(self.success_url)
    
    
    



@require_POST
@login_required
def mark_appointment_completed(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    appointment.status = 'COMPLETED'
    appointment.save()
    
    # Check if bill already exists
    if not hasattr(appointment, 'bill'):
        messages.info(request, 'Appointment marked as completed. Would you like to create a bill?')
        
        return redirect('DurielMedicApp:create_bill_for_appointment', appointment_id=appointment.pk)
    
    messages.success(request, 'Appointment marked as completed.')
    return redirect('DurielMedicApp:appointment_list')


@require_POST
@login_required
def mark_appointment_cancelled(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    appointment.status = 'CANCELLED'
    appointment.save()
    messages.warning(request, 'Appointment marked as cancelled.')
    return redirect('DurielMedicApp:appointment_list')

    



# Staff Management Views
@login_required
@user_passes_test(admin_check, login_url='login')
def staff_list(request):
    staff = CustomUser.objects.filter(is_staff=True).exclude(role='ADMIN')
    return render(request, 'staff/staff_list.html', {'staff': staff})

class StaffCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = CustomUser
    form_class = CustomUserCreationForm
    template_name = 'staff/staff_form.html'
    success_url = reverse_lazy('staff_list')
    
    def test_func(self):
        return self.request.user.is_authenticated and admin_check(self.request.user)
    
    def form_valid(self, form):
        form.instance.is_staff = True
        messages.success(self.request, 'Staff member added successfully!')
        return super().form_valid(form)
    
    
@login_required
def patient_list(request):
    patients = Patient.objects.all()
    return render(request, 'patients/patient_list.html', {'patients': patients})


@login_required
@role_required('ADMIN', 'DOCTOR', 'NURSE')
def add_medical_record(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    if request.method == 'POST':
        form = MedicalRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.patient = patient
            record.created_by = request.user
            record.save()
            messages.success(request, 'Medical record added successfully!')
            return redirect('DurielMedicApp:patient_detail', pk=patient.pk)
    else:
        form = MedicalRecordForm()
    
    return render(request, 'medical_records/add_medical_record.html', {
        'form': form,
        'patient': patient
    })

@login_required
@role_required('ADMIN', 'DOCTOR', 'NURSE')
def edit_medical_record(request, record_id):
    record = get_object_or_404(MedicalRecord, pk=record_id)
    if request.method == 'POST':
        form = MedicalRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, 'Medical record updated successfully!')
            return redirect('DurielMedicApp:patient_detail', pk=record.patient.pk)
    else:
        form = MedicalRecordForm(instance=record)
    
    return render(request, 'medical_records/edit_medical_record.html', {
        'form': form,
        'record': record
    })

@login_required
@role_required('ADMIN', 'DOCTOR')
def delete_medical_record(request, record_id):
    record = get_object_or_404(MedicalRecord, pk=record_id)
    patient_id = record.patient.pk
    record.delete()
    messages.success(request, 'Medical record deleted successfully!')
    return redirect('DurielMedicApp:patient_detail', pk=patient_id)



def patient_search_api(request):
    query = request.GET.get('q', '')
    results = Patient.objects.filter(full_name__icontains=query)
    data = [{'id': p.id, 'name': p.full_name} for p in results]
    return JsonResponse({'results': data})




# Appointment List View
# 1. List all appointments (for staff/admin)
@login_required
def appointment_list(request):
    appointments = Appointment.objects.all().order_by('-date')
    return render(request, 'appointments/appointment_list.html', {'appointments': appointments})


# 2. Create new appointment
@login_required
def appointment_create(request):
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Appointment scheduled successfully.')
            return redirect('appointment_list')
    else:
        form = AppointmentForm()
    
    return render(request, 'appointments/appointment_form.html', {'form': form})


# 3. Update appointment
@login_required
def appointment_update(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    
    form = AppointmentForm(request.POST or None, instance=appointment)
    if form.is_valid():
        form.save()
        messages.success(request, 'Appointment updated successfully.')
        return redirect('DurielMedicApp:appointment_list')
    
    return render(request, 'appointments/appointment_form.html', {'form': form})


# 4. Delete appointment
@login_required
def appointment_delete(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    
    if request.method == 'POST':
        appointment.delete()
        messages.success(request, 'Appointment deleted successfully.')
        return redirect('DurielMedicApp:appointment_list')
    
    return render(request, 'appointments/appointment_confirm_delete.html', {'appointment': appointment})


# 5. Check appointment availability via API
@login_required
def check_appointment_availability(request):
    provider_id = request.GET.get('provider')
    date = request.GET.get('date')
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    
    if not all([provider_id, date, start_time, end_time]):
        return JsonResponse({'available': False, 'error': 'Missing required parameters'}, status=400)
    
    try:
        overlapping = Appointment.objects.filter(
            provider_id=provider_id,
            date=date,
            start_time__lt=end_time,
            end_time__gt=start_time
        )
        available = not overlapping.exists()
        return JsonResponse({'available': available})
    except Exception as e:
        return JsonResponse({'available': False, 'error': str(e)}, status=500)


@login_required
def add_appointment(request):
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.provider = request.user

            if request.user.clinic is None:
                messages.error(request, "Your account is not assigned to a clinic. Please contact the admin.")
                return redirect('DurielMedicApp:add_appointment')

            appointment.clinic = request.user.clinic
            appointment.status = 'SCHEDULED'
            appointment.save()

            # ✅ Reset patient status to REGISTERED for fresh visit
            appointment.patient.status = 'REGISTERED'
            appointment.patient.save()

            # Notify all active users
            from django.contrib.auth import get_user_model
            User = get_user_model()
            staff_users = User.objects.filter(is_active=True)
            for user in staff_users:
                Notification.objects.create(
                    user=user,
                    message=f"New appointment with {appointment.patient.full_name} on {appointment.date}",
                    link=reverse('DurielMedicApp:appointment_list')
                )

            messages.success(request, 'Appointment scheduled successfully!')
            return redirect('DurielMedicApp:appointment_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = AppointmentForm(initial={'provider': request.user})

    return render(request, 'appointments/add_appointment.html', {
        'form': form,
        'title': 'Add New Appointment',
    })





# Notification Views


def check_birthdays():
    today = date.today()
    patients = Patient.objects.filter(
        date_of_birth__month=today.month,
        date_of_birth__day=today.day
    )
    
    for patient in patients:
        # Create notification for staff
        Notification.objects.create(
            user=patient.created_by,
            message=f"Today is {patient.full_name}'s birthday!",
            link=reverse('DurielMedicApp:patient_detail', kwargs={'pk': patient.pk})
        )
        
        # Send email if email exists
        if patient.email:
            send_mail(
                'Happy Birthday!',
                f'Dear {patient.full_name},\n\nHappy Birthday from DurielMedic+!',
                settings.DEFAULT_FROM_EMAIL,
                [patient.email],
                fail_silently=True
            )
        
        # Here you could add SMS functionality if you have an SMS service integrated
        
        
        
        
# @require_POST
# @login_required
# def mark_notification_read(request):
#     request.user.notifications.filter(is_read=False).update(is_read=True)
#     return JsonResponse({'status': 'success'})


from django.views.decorators.csrf import csrf_exempt

@login_required
@csrf_exempt
def mark_notification_read(request):
    # Mark personal notifications
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)

    # Mark global notifications as read per user
    unread_globals = Notification.objects.filter(user__isnull=True).exclude(
        id__in=NotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
    )
    NotificationRead.objects.bulk_create([
        NotificationRead(user=request.user, notification=n) for n in unread_globals
    ], ignore_conflicts=True)

    return JsonResponse({'status': 'success'})



@login_required
def clear_notifications(request):
    # Delete user-specific notifications
    request.user.notifications.all().delete()

    # Mark global as read (don't delete them)
    unread_globals = Notification.objects.filter(user__isnull=True).exclude(
        id__in=NotificationRead.objects.filter(user=request.user).values_list('notification_id', flat=True)
    )
    NotificationRead.objects.bulk_create([
        NotificationRead(user=request.user, notification=n) for n in unread_globals
    ], ignore_conflicts=True)

    messages.success(request, "Notifications cleared")
    return redirect(request.META.get('HTTP_REFERER', 'DurielMedicApp:dashboard'))


# @login_required
# def mark_notification_read(request, pk):
#     notification = get_object_or_404(Notification, pk=pk, user=request.user)
#     notification.is_read = True
#     notification.save()
#     return redirect(notification.link or 'DurielMedicApp:dashboard')


from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.utils.timezone import make_aware
from datetime import datetime, timedelta, time
from django.db.models import Count, Sum
from django.http import HttpResponse
import csv

from .models import Appointment, Patient, Billing  # adjust if needed
from .utils import admin_check  # or define your own admin_check function


@login_required
@user_passes_test(admin_check, login_url='login')
def generate_report(request):
    # Default date range: last 30 days
    end_date = timezone.now()
    start_date = end_date - timedelta(days=30)

    if request.method == 'POST':
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        report_type = request.POST.get('report_type')

        if start_date_str and end_date_str:
            start_date = make_aware(datetime.combine(datetime.strptime(start_date_str, '%Y-%m-%d'), time.min))
            end_date = make_aware(datetime.combine(datetime.strptime(end_date_str, '%Y-%m-%d'), time.max))

        # Route to correct report
        if report_type == 'appointments':
            return generate_appointment_report(start_date, end_date)
        elif report_type == 'patients':
            return generate_patient_report(start_date, end_date)
        elif report_type == 'financial':
            return generate_financial_report(start_date, end_date)

    # Dashboard Summary Stats
    appointment_stats = Appointment.objects.filter(
        date__range=[start_date.date(), end_date.date()]
    ).values('status').annotate(count=Count('id'))

    patient_stats = Patient.objects.filter(
        created_at__range=[start_date, end_date]
    ).aggregate(total=Count('patient_id'))

    financial_stats = Billing.objects.filter(
        service_date__range=[start_date.date(), end_date.date()]
    ).aggregate(
        total_amount=Sum('amount'),
        total_paid=Sum('paid_amount')
    )

    context = {
        'start_date': start_date.date(),
        'end_date': end_date.date(),
        'appointment_stats': appointment_stats,
        'patient_stats': patient_stats,
        'financial_stats': financial_stats,
    }

    return render(request, 'reports/generate_report.html', context)


def generate_appointment_report(start_date, end_date):
    appointments = Appointment.objects.filter(
        date__range=[start_date.date(), end_date.date()]
    ).select_related('patient', 'provider').order_by('date', 'start_time')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="appointments_report_{start_date.date()}_to_{end_date.date()}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Date', 'Time', 'Patient', 'Provider', 'Status', 'Reason'])

    for appt in appointments:
        writer.writerow([
            appt.date,
            f"{appt.start_time} - {appt.end_time}",
            appt.patient.full_name,
            appt.provider.get_full_name(),
            appt.get_status_display(),
            appt.reason
        ])

    return response


def generate_patient_report(start_date, end_date):
    patients = Patient.objects.filter(
        created_at__range=[start_date, end_date]
    ).order_by('created_at')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="patients_report_{start_date.date()}_to_{end_date.date()}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Patient ID', 'Name', 'Gender', 'Date of Birth', 'Contact', 'Registered On'])

    for patient in patients:
        writer.writerow([
            patient.patient_id,
            patient.full_name,
            patient.get_gender_display(),
            patient.date_of_birth,
            patient.contact,
            patient.created_at.strftime('%Y-%m-%d %H:%M')
        ])

    return response


def generate_financial_report(start_date, end_date):
    try:
        bills = Billing.objects.filter(
            service_date__range=[start_date.date(), end_date.date()]
        ).select_related('patient').order_by('service_date')

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="financial_report_'
            f'{start_date.date()}_to_{end_date.date()}.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(['Bill Date', 'Patient', 'Amount', 'Paid', 'Balance', 'Status', 'Description'])

        for bill in bills:
            amount = bill.amount or 0
            paid = bill.paid_amount or 0
            balance = amount - paid

            writer.writerow([
                bill.service_date.strftime('%Y-%m-%d') if bill.service_date else '',
                bill.patient.full_name if bill.patient else 'Unknown Patient',
                amount,
                paid,
                balance,
                bill.get_status_display() if bill.status else '',
                bill.description or ''
            ])

        return response

    except Exception as e:
        print(f"Error generating financial report: {str(e)}")
        return HttpResponse(
            "An error occurred while generating the report. Please try again later.",
            content_type='text/plain',
            status=500
        )
        


from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from django.db import transaction

@login_required
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
@role_required('ADMIN', 'RECEPTIONIST')
def create_bill(request, patient_id=None, appointment_id=None):
    patient = None
    appointment = None
    
    # Get patient and appointment objects
    if appointment_id:
        appointment = get_object_or_404(Appointment, pk=appointment_id)
        patient = appointment.patient
    
    if patient_id and not patient:
        patient = get_object_or_404(Patient, pk=patient_id)
    
    # Get patients with appointments for dropdown
    patients_with_appointments = Patient.objects.filter(
        appointments__isnull=False
    ).distinct()
    
    if request.method == 'POST':
        form = BillingForm(request.POST)
        if form.is_valid():
            bill = form.save(commit=False)
            
            # Ensure patient is set
            if not bill.patient:
                if patient:
                    bill.patient = patient
                else:
                    form.add_error('patient', 'Patient is required')
                    return render(request, 'billing/billing_form.html', {
                        'form': form,
                        'patient': patient,
                        'appointment': appointment,
                        'patients_with_appointments': patients_with_appointments,
                        'title': 'Create New Bill'
                    })
            
            # Set appointment if available
            if appointment:
                bill.appointment = appointment
            
            bill.created_by = request.user
            
            # Initialize paid_amount to 0 if not provided
            if not bill.paid_amount:
                bill.paid_amount = 0
                
            # Validate payment amount
            if bill.paid_amount > bill.amount:
                form.add_error('paid_amount', "Paid amount cannot be greater than total amount")
                return render(request, 'billing/billing_form.html', {
                    'form': form,
                    'patient': patient,
                    'appointment': appointment,
                    'patients_with_appointments': patients_with_appointments,
                    'title': 'Create New Bill'
                })
            
            # Calculate status
            if bill.paid_amount == bill.amount:
                bill.status = 'PAID'
            elif bill.paid_amount > 0:
                bill.status = 'PARTIAL'
            else:
                bill.status = 'PENDING'
            
            try:
                bill.save()
                messages.success(request, "Bill created successfully!")
                return redirect('DurielMedicApp:billing_list')
            except Exception as e:
                form.add_error(None, f"Error saving bill: {str(e)}")
    else:
        initial = {
            'patient': patient.pk if patient else None,
            'appointment': appointment.id if appointment else None,
            'description': f"Consultation for {appointment.reason}" if appointment else "",
            'service_date': date.today(),
            'due_date': date.today() + timedelta(days=14)
        }
        form = BillingForm(initial=initial)
    
    return render(request, 'billing/billing_form.html', {
        'form': form,
        'patient': patient,
        'appointment': appointment,
        'patients_with_appointments': patients_with_appointments,
        'title': 'Create New Bill'
    })
    
    
    
@login_required
@role_required('ADMIN', 'RECEPTIONIST', 'DOCTOR', 'NURSE')
def view_bill(request, pk):
    bill = get_object_or_404(Billing, pk=pk)
    return render(request, 'billing/bill_detail.html', {'bill': bill})





@login_required
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
            
            # Recalculate status based on payment
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
            return redirect('DurielMedicApp:view_bill', pk=bill.pk)
    else:
        form = BillingForm(instance=bill)
    
    return render(request, 'billing/billing_form.html', {
        'form': form,
        'bill': bill,
        'patients_with_appointments': patients_with_appointments,
        'title': 'Edit Bill'
    })
    
    
from decimal import Decimal

@login_required
@role_required('ADMIN', 'RECEPTIONIST')
def record_payment(request, pk):
    bill = get_object_or_404(Billing, pk=pk)
    
    if request.method == 'POST':
        payment_amount = Decimal(request.POST.get('payment_amount', '0'))
        
        if payment_amount <= 0:
            messages.error(request, "Payment amount must be greater than zero")
            return redirect('DurielMedicApp:view_bill', pk=bill.pk)
        
        if payment_amount > (bill.amount - bill.paid_amount):
            messages.error(request, "Payment amount exceeds outstanding balance")
            return redirect('DurielMedicApp:view_bill', pk=bill.pk)
        
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
        
        return redirect('DurielMedicApp:view_bill', pk=bill.pk)
    
    return render(request, 'billing/record_payment.html', {'bill': bill})

@login_required
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


@login_required
@role_required('ADMIN', 'RECEPTIONIST')
def delete_bill(request, pk):
    bill = get_object_or_404(Billing, pk=pk)
    
    if request.method == 'POST':
        bill.delete()
        messages.success(request, "Bill deleted successfully!")
        return redirect('DurielMedicApp:billing_list')
    
    return render(request, 'billing/confirm_delete.html', {'bill': bill})


        






def logout_view(request):
    logout(request)
    return redirect('login') 