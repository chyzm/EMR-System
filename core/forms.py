from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from core.models import CustomUser, Patient, Billing, Payment, Clinic, Prescription
from django.core.exceptions import ValidationError
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column
from django.contrib.auth.forms import AuthenticationForm
from datetime import date

from django import forms

class CustomUserCreationForm(UserCreationForm):
    clinic = forms.ModelMultipleChoiceField(
        queryset=Clinic.objects.all(),
        widget=forms.CheckboxSelectMultiple,  # or SelectMultiple
        required=False,
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'license_number', 'specialization', 'phone', 'clinic')

    
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
    clinic = forms.ModelMultipleChoiceField(
        queryset=Clinic.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2', 
                 'role', 'title', 'phone', 'clinic', 'is_active', 'is_staff', 'verified', 'is_superuser', 'profile_picture']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'password1': forms.PasswordInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'password2': forms.PasswordInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'role': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'title': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
            }),
            'is_staff': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
            }),
            'verified': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
            }),
            'is_superuser': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
            }),
            'profile_picture': forms.FileInput(attrs={
                'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'
            }),
        }
        
        def __init__(self, *args, **kwargs):
            self.request = kwargs.pop('request', None)
            super().__init__(*args, **kwargs)
            
            # Hide and disable is_superuser field if user is not a superuser
            if self.request and not self.request.user.is_superuser:
                self.fields['is_superuser'].widget = forms.HiddenInput()
                self.fields['is_superuser'].disabled = True
                self.fields['is_superuser'].initial = False
            
            

class UserEditForm(forms.ModelForm):
    clinic = forms.ModelMultipleChoiceField(
        queryset=Clinic.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    
    class Meta:
        model = CustomUser
        fields = ['title', 'first_name', 'last_name', 'email', 'phone', 
                 'is_active', 'is_staff', 'verified', 
                 'is_superuser', 'clinic', 'role', 'profile_picture']
        widgets = {
            'title': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'role': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
            }),
            'is_staff': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
            }),
            'is_superuser': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
            }),
            'verified': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
            }),
            'profile_picture': forms.FileInput(attrs={
                'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'
            }),
            
        }
        
        
        def __init__(self, *args, **kwargs):
            self.request = kwargs.pop('request', None)
            super().__init__(*args, **kwargs)
            
            # Hide and disable is_superuser field if user is not a superuser
            if self.request and not self.request.user.is_superuser:
                self.fields['is_superuser'].widget = forms.HiddenInput()
                self.fields['is_superuser'].disabled = True

from django.utils import timezone

class PatientForm(forms.ModelForm):
    email = forms.EmailField(required=False)  # <-- Add this line
    class Meta:
        model = Patient
        fields = '__all__'
        exclude = ['created_by', 'clinic', 'patient_id']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'})
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Make fields optional if needed
        self.fields['blood_group'].required = False
        self.fields['allergies'].required = False
        self.fields['emergency_contact_name'].required = False
        self.fields['profile_picture'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        if self.request:
            instance.created_by = self.request.user
            clinic_id = self.request.session.get('clinic_id')
            if clinic_id:
                instance.clinic_id = clinic_id
            
            # Set created_at if not set
            if not instance.created_at:
                instance.created_at = timezone.now()
        
        if commit:
            instance.save()
        
        return instance
        
    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')

        if dob is None:
            raise ValidationError("Please enter a valid date for Date of Birth.")

        if dob > date.today():
            raise ValidationError("Date of Birth cannot be in the future.")

        return dob

class BillingForm(forms.ModelForm):
    class Meta:
        model = Billing
        fields = ['patient', 'appointment', 'service_date', 'due_date', 'amount', 'paid_amount', 'description']
        widgets = {
            'service_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['patient'].required = True
        if not self.instance.pk:
            self.initial['paid_amount'] = 0

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'payment_method', 'transaction_reference', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.billing = kwargs.pop('billing', None)
        super().__init__(*args, **kwargs)
        
        if self.billing:
            self.fields['amount'].widget.attrs.update({
                'max': self.billing.get_balance(),
                'min': 0.01,
                'step': '0.01',
                'class': 'form-control'
            })
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if self.billing and amount > self.billing.get_balance():
            raise forms.ValidationError(f"Payment amount exceeds outstanding balance of ₦{self.billing.get_balance():.2f}")
        return amount
    
    
    
class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ['patient', 'medication', 'dosage', 'frequency', 'duration', 'instructions']
        widgets = {
            'instructions': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }
    
    
    


from django import forms
from .models import Clinic

class ClinicForm(forms.ModelForm):
    class Meta:
        model = Clinic
        fields = ['name', 'clinic_type', 'address']
        
        
from django import forms
from .models import Clinic
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _
import os

class ClinicLogoForm(forms.ModelForm):
    class Meta:
        model = Clinic
        fields = ['logo']
    
    def clean_logo(self):
        logo = self.cleaned_data.get('logo', False)
        if logo:
            # Check if we have a new file upload (not existing ImageFieldFile)
            if hasattr(logo, 'file'):  # This is a new upload
                # Size validation
                if logo.size > 1*1024*1024:  # 1MB limit
                    raise forms.ValidationError(_(
                        f'File size must be under 1MB. Your file is {filesizeformat(logo.size)}'
                    ))
                
                # Get the file extension for type validation
                valid_extensions = ['.jpg', '.jpeg', '.png']
                ext = os.path.splitext(logo.name)[1].lower()
                if ext not in valid_extensions:
                    raise forms.ValidationError(_(
                        'Unsupported file type. Please upload a JPG or PNG image.'
                    ))
            
            return logo
        return None
        
        
        
