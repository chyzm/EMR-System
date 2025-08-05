from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import CustomUser, Patient, Appointment, Prescription, MedicalRecord, Billing
from django.core.exceptions import ValidationError
from django.utils import timezone
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Field
from django.contrib.auth.forms import AuthenticationForm
from .models import Vitals, Admission, FollowUp



# class StyledLoginForm(AuthenticationForm):
#     username = forms.CharField(
#         widget=forms.TextInput(attrs={
#             'class': 'block w-full border border-gray-300 rounded-md px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500',
#             'placeholder': 'Enter your username',
#         })
#     )
#     password = forms.CharField(
#         widget=forms.PasswordInput(attrs={
#             'class': 'block w-full border border-gray-300 rounded-md px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500',
#             'placeholder': 'Enter your password',
#         })
#     )

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'license_number', 'specialization', 'phone')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('username', css_class='form-group col-md-6 mb-0'),
                Column('email', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('first_name', css_class='form-group col-md-6 mb-0'),
                Column('last_name', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('role', css_class='form-group col-md-4 mb-0'),
                Column('license_number', css_class='form-group col-md-4 mb-0'),
                Column('specialization', css_class='form-group col-md-4 mb-0'),
                css_class='form-row'
            ),
            'phone',
            Row(
                Column('password1', css_class='form-group col-md-6 mb-0'),
                Column('password2', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Submit('submit', 'Create Account')
        )
        
class UserCreationWithRoleForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ['title', 'username', 'email', 'first_name', 'last_name', 'phone', 'role', 'clinic', 'password1', 'password2', 'is_active']
        widgets = {
            'title': forms.Select(attrs={
                'class': 'w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
            }),
            'username': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
            }),
            'role': forms.Select(attrs={
                'class': 'w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
            }),
            'clinic': forms.Select(attrs={
                'class': 'w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
            }),
            'is_active': forms.Select(choices=[(True, 'Active'), (False, 'Inactive')], attrs={
                'class': 'w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
            }),
        }

    def __init__(self, *args, **kwargs):
        super(UserCreationWithRoleForm, self).__init__(*args, **kwargs)
        # Style the password fields too
        self.fields['password1'].widget.attrs.update({
            'class': 'w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
        })
        





class UserEditForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['title', 'first_name', 'last_name', 'email', 'phone','is_active', 'clinic', 'role']  # add any other custom fields
        widgets = {
            'title': forms.Select(attrs={'class': 'w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'first_name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded'}),
            'last_name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded'}),
            'email': forms.EmailInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded'}),
            'clinic': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded'}),
            'role': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded'}),
            'is_active': forms.Select(choices=[(True, 'Active'), (False, 'Inactive')], attrs={'class': 'w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'phone': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded'}),
        }



class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = '__all__'
        exclude = ['created_by', 'clinic', 'patient_id']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'allergies': forms.Textarea(attrs={'rows': 2}),
            'address': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('full_name', css_class='form-group col-md-6 mb-0'),
                Column('date_of_birth', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('gender', css_class='form-group col-md-4 mb-0'),
                Column('blood_group', css_class='form-group col-md-4 mb-0'),
                Column('contact', css_class='form-group col-md-4 mb-0'),
                css_class='form-row'
            ),
            'address',
            Row(
                Column('emergency_contact', css_class='form-group col-md-6 mb-0'),
                Column('emergency_contact_name', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'allergies',
            'profile_picture',
            Submit('submit', 'Save Patient')
        )
        
        


class VitalsForm(forms.ModelForm):
    class Meta:
        model = Vitals
        fields = '__all__'
        widgets = {
            'appointment': forms.HiddenInput(),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        

class FollowUpForm(forms.ModelForm):
    class Meta:
        model = FollowUp
        fields = ['reason', 'scheduled_date', 'scheduled_time', 'notes']
        widgets = {
            'scheduled_date': forms.DateInput(attrs={'type': 'date'}),
            'scheduled_time': forms.TimeInput(attrs={'type': 'time'}),
            'reason': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        

class AdmissionForm(forms.ModelForm):
    class Meta:
        model = Admission
        fields = '__all__'
        widgets = {
            'patient': forms.HiddenInput(),
            'reason': forms.Textarea(attrs={'rows': 3}),
        }

class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['patient', 'provider', 'date', 'start_time', 'end_time', 'reason', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
            'reason': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get('date')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        provider = cleaned_data.get('provider')
        
        if date and date < timezone.now().date():
            raise ValidationError("Appointment date cannot be in the past.")
        
        if start_time and end_time and start_time >= end_time:
            raise ValidationError("End time must be after start time.")
        
        # Check for overlapping appointments
        if provider and date and start_time and end_time:
            overlapping = Appointment.objects.filter(
                provider=provider,
                date=date,
                start_time__lt=end_time,
                end_time__gt=start_time
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if overlapping.exists():
                raise ValidationError("This provider already has an appointment scheduled during this time.")

class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ['patient', 'medication', 'dosage', 'frequency', 'duration', 'instructions']
        widgets = {
            'instructions': forms.Textarea(attrs={'rows': 3}),
        }
        

class MedicalRecordForm(forms.ModelForm):
    class Meta:
        model = MedicalRecord
        fields = ['record_type', 'title', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-textarea'}),
            'record_type': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('record_type', css_class='form-group col-md-6 mb-0'),
                Column('title', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'description',
            Submit('submit', 'Save Record')
        )
        


class BillingForm(forms.ModelForm):
    class Meta:
        model = Billing
        fields = [
            'patient',
            'appointment',
            'amount',
            'paid_amount',
            'status',
            'service_date',
            'due_date',
            'description',
        ]
        widgets = {
            'service_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'paid_amount': 'Amount Paid',
        }

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get('amount')
        paid_amount = cleaned.get('paid_amount')
        service_date = cleaned.get('service_date')
        due_date = cleaned.get('due_date')
        status = cleaned.get('status')

        # Amount validations
        if amount is not None and amount < 0:
            self.add_error('amount', 'Amount cannot be negative.')

        if paid_amount is not None:
            if paid_amount < 0:
                self.add_error('paid_amount', 'Paid amount cannot be negative.')
            if amount is not None and paid_amount > amount:
                self.add_error('paid_amount', 'Paid amount cannot exceed total amount.')

        # Date validation
        if service_date and due_date and due_date < service_date:
            self.add_error('due_date', 'Due date cannot be before the service date.')

        # Status consistency checks (optional but helpful)
        if amount is not None and paid_amount is not None and status:
            if paid_amount == 0 and status not in ('PENDING', 'CANCELLED'):
                self.add_error('status', 'Use PENDING or CANCELLED when no payment has been made.')
            elif 0 < paid_amount < amount and status != 'PARTIAL':
                self.add_error('status', 'Use PARTIAL for partially paid bills.')
            elif paid_amount == amount and status != 'PAID':
                self.add_error('status', 'Use PAID when the bill is fully settled.')

        return cleaned
