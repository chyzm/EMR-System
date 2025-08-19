from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from core.models import CustomUser, Patient, Billing, Payment, Clinic, Prescription, ServicePriceList
from django.core.exceptions import ValidationError
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column
from django.contrib.auth.forms import AuthenticationForm
from datetime import date





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

# class UserCreationWithRoleForm(UserCreationForm):
#     clinic = forms.ModelMultipleChoiceField(
#         queryset=Clinic.objects.all(),
#         widget=forms.CheckboxSelectMultiple,
#         required=False,
#     )
    
#     class Meta:
#         model = CustomUser
#         fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2', 
#                  'role', 'title', 'phone', 'clinic', 'is_active', 'is_staff', 'verified', 'is_superuser', 'profile_picture']
#         widgets = {
#             'username': forms.TextInput(attrs={
#                 'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
#             }),
#             'email': forms.EmailInput(attrs={
#                 'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
#             }),
#             'first_name': forms.TextInput(attrs={
#                 'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
#             }),
#             'last_name': forms.TextInput(attrs={
#                 'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
#             }),
#             'password1': forms.PasswordInput(attrs={
#                 'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
#             }),
#             'password2': forms.PasswordInput(attrs={
#                 'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
#             }),
#             'role': forms.Select(attrs={
#                 'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
#             }),
#             'title': forms.Select(attrs={
#                 'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
#             }),
#             'phone': forms.TextInput(attrs={
#                 'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
#             }),
#             'is_active': forms.CheckboxInput(attrs={
#                 'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
#             }),
#             'is_staff': forms.CheckboxInput(attrs={
#                 'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
#             }),
#             'verified': forms.CheckboxInput(attrs={
#                 'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
#             }),
#             'is_superuser': forms.CheckboxInput(attrs={
#                 'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
#             }),
#             'profile_picture': forms.FileInput(attrs={
#                 'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'
#             }),
#         }
        
#     # MOVED OUTSIDE Meta class - this was the issue!
#     def __init__(self, *args, **kwargs):
#         # Extract the request from kwargs before calling super()
#         self.request = kwargs.pop('request', None)
#         super().__init__(*args, **kwargs)

#         # Hide superuser checkbox for non-superusers
#         if self.request and not self.request.user.is_superuser:
#             self.fields['is_superuser'].widget = forms.HiddenInput()
#             self.fields['is_superuser'].disabled = True
#             self.fields['is_superuser'].initial = False


class UserCreationWithRoleForm(UserCreationForm):
    clinic = forms.ModelMultipleChoiceField(
        queryset=Clinic.objects.none(),  # Start with empty queryset
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2', 
                 'role', 'title', 'phone', 'clinic', 'is_active', 'is_staff', 'verified', 'is_superuser', 'profile_picture']
        widgets = {
            # ... existing widget definitions ...
        }
        
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Set clinic queryset based on the request user
        if self.request:
            if self.request.user.is_superuser:
                self.fields['clinic'].queryset = Clinic.objects.all()
            else:
                self.fields['clinic'].queryset = self.request.user.clinic.all()
            
            # Hide superuser checkbox for non-superusers
            if not self.request.user.is_superuser:
                self.fields['is_superuser'].widget = forms.HiddenInput()
                self.fields['is_superuser'].disabled = True
                self.fields['is_superuser'].initial = False
                
                

# class UserEditForm(forms.ModelForm):
#     clinic = forms.ModelMultipleChoiceField(
#         queryset=Clinic.objects.all(),
#         widget=forms.CheckboxSelectMultiple,
#         required=False,
#     )
    
#     class Meta:
#         model = CustomUser
#         fields = ['title', 'first_name', 'last_name', 'email', 'phone', 
#                  'is_active', 'is_staff', 'verified', 
#                  'is_superuser', 'clinic', 'role', 'profile_picture']
        # widgets = {
        #     'title': forms.Select(attrs={
        #         'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
        #     }),
        #     'first_name': forms.TextInput(attrs={
        #         'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
        #     }),
        #     'last_name': forms.TextInput(attrs={
        #         'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
        #     }),
        #     'email': forms.EmailInput(attrs={
        #         'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
        #     }),
        #     'role': forms.Select(attrs={
        #         'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
        #     }),
        #     'is_active': forms.CheckboxInput(attrs={
        #         'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
        #     }),
        #     'is_staff': forms.CheckboxInput(attrs={
        #         'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
        #     }),
        #     'is_superuser': forms.CheckboxInput(attrs={
        #         'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
        #     }),
        #     'verified': forms.CheckboxInput(attrs={
        #         'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
        #     }),
        #     'phone': forms.TextInput(attrs={
        #         'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors'
        #     }),
        #     'profile_picture': forms.FileInput(attrs={
        #         'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'
        #     }),
        # }
        
#     # MOVED OUTSIDE Meta class - same issue here!        
#     def __init__(self, *args, **kwargs):
#         self.request = kwargs.pop('request', None)
#         super().__init__(*args, **kwargs)
        
#         # Hide and disable is_superuser field if user is not a superuser
#         if self.request and not self.request.user.is_superuser:
#             self.fields['is_superuser'].widget = forms.HiddenInput()
#             self.fields['is_superuser'].disabled = True



class UserEditForm(forms.ModelForm):
    clinic = forms.ModelMultipleChoiceField(
        queryset=Clinic.objects.none(),  # Start with empty queryset
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
        
        # Set clinic queryset based on the request user
        if self.request:
            if self.request.user.is_superuser:
                self.fields['clinic'].queryset = Clinic.objects.all()
            else:
                self.fields['clinic'].queryset = self.request.user.clinic.all()
            
            # Hide and disable is_superuser field if user is not a superuser
            if not self.request.user.is_superuser:
                self.fields['is_superuser'].widget = forms.HiddenInput()
                self.fields['is_superuser'].disabled = True
            
            
            
            
            
            
            
from django.utils import timezone

class PatientForm(forms.ModelForm):
    email = forms.EmailField(required=False)
    
    class Meta:
        model = Patient
        fields = '__all__'
        exclude = ['created_by', 'clinic', 'patient_id', 'full_name']  # Add full_name to exclude
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'status': forms.Select(attrs={
                'class': 'mt-1 block w-full pl-3 pr-10 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Make fields optional if needed
        self.fields['blood_group'].required = False
        self.fields['allergies'].required = True
        self.fields['emergency_contact_name'].required = False
        self.fields['profile_picture'].required = False
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set the full_name property from first_name and last_name
        # instance.full_name = f"{instance.first_name} {instance.last_name}"
        
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
    services = forms.ModelMultipleChoiceField(
        queryset=ServicePriceList.objects.none(),
        widget=forms.SelectMultiple(attrs={'class': 'form-control select2'}),
        required=False
    )

    class Meta:
        model = Billing
        fields = ['patient', 'appointment', 'service_date', 'due_date', 'amount', 'paid_amount', 'description']
        widgets = {
            'service_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        clinic_id = kwargs.pop('clinic_id', None)
        super().__init__(*args, **kwargs)
        
        if clinic_id:
            self.fields['services'].queryset = ServicePriceList.objects.filter(
                clinic_id=clinic_id, 
                is_active=True
            ).order_by('name')
            
        if not self.instance.pk:
            self.initial['paid_amount'] = 0







            
class ServicePriceListForm(forms.ModelForm):
    class Meta:
        model = ServicePriceList
        fields = ['name', 'description', 'price', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        
        
        

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
    
    
    
# class PrescriptionForm(forms.ModelForm):
#     class Meta:
#         model = Prescription
#         fields = ['patient', 'medication', 'dosage', 'frequency', 'duration', 'instructions']
#         widgets = {
#             'instructions': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
#         }


# Add these forms to your existing forms.py

from django import forms
from .models import ClinicMedication, MedicationCategory, Prescription, StockMovement

class ClinicMedicationForm(forms.ModelForm):
    class Meta:
        model = ClinicMedication
        fields = [
            'name', 'generic_name', 'category', 'medication_type', 
            'strength', 'manufacturer', 'quantity_in_stock', 
            'minimum_stock_level', 'cost_price', 'selling_price', 
            'expiry_date', 'batch_number', 'status'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Medication name'}),
            'generic_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Generic name (optional)'}),
            'strength': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 500mg, 10ml'}),
            'manufacturer': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Manufacturer name'}),
            'quantity_in_stock': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'minimum_stock_level': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'value': '10'}),
            'cost_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'batch_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Batch/Lot number'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'medication_type': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }
    
    # def __init__(self, *args, **kwargs):
    #     self.clinic = kwargs.pop('clinic', None)
    #     super().__init__(*args, **kwargs)
        
    #     # Set clinic automatically if provided
    #     if self.clinic:
    #         self.instance.clinic = self.clinic
    
    def __init__(self, *args, **kwargs):
        clinic = kwargs.pop('clinic', None)
        super().__init__(*args, **kwargs)
        
        if clinic:
            # Only show categories for the current clinic
            self.fields['category'].queryset = MedicationCategory.objects.filter(clinic=clinic)
        else:
            # If no clinic provided, show empty queryset
            self.fields['category'].queryset = MedicationCategory.objects.none()
        
        # Make category optional with empty label
        self.fields['category'].empty_label = "Select Category (Optional)"
        self.fields['category'].required = False


class StockAdjustmentForm(forms.Form):
    """Form for adjusting stock levels"""
    ADJUSTMENT_TYPES = (
        ('ADD', 'Add Stock'),
        ('REMOVE', 'Remove Stock'),
        ('SET', 'Set Stock Level'),
    )
    
    adjustment_type = forms.ChoiceField(
        choices=ADJUSTMENT_TYPES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    quantity = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Reason for adjustment'})
    )


class PrescriptionForm(forms.ModelForm):
    """Enhanced prescription form with clinic medication support and Tailwind styling"""
    
    class Meta:
        model = Prescription
        fields = [
            'patient', 'clinic_medication', 'custom_medication', 
            'dosage', 'frequency', 'duration', 'quantity_prescribed', 'instructions'
        ]
        widgets = {
            'patient': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm'
            }),
            'clinic_medication': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm'
            }),
            'custom_medication': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm',
                'placeholder': 'Enter custom medication name'
            }),
            'dosage': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm',
                'placeholder': 'e.g., 1 tablet'
            }),
            'frequency': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm',
                'placeholder': 'e.g., Twice daily'
            }),
            'duration': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm',
                'placeholder': 'e.g., 7 days'
            }),
            'quantity_prescribed': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm',
                'min': '1',
                'value': '1'
            }),
            'instructions': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm',
                'rows': 3,
                'placeholder': 'Special instructions'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.clinic = kwargs.pop('clinic', None)
        super().__init__(*args, **kwargs)

        if self.clinic:
            medications = ClinicMedication.objects.filter(
                clinic=self.clinic, 
                status='ACTIVE'
            ).order_by('name')

            choices = [('', 'Select from clinic inventory')]
            for med in medications:
                stock_info = ""
                if med.is_out_of_stock:
                    stock_info = " (OUT OF STOCK)"
                elif med.is_low_stock:
                    stock_info = f" (LOW STOCK: {med.quantity_in_stock})"
                else:
                    stock_info = f" (Stock: {med.quantity_in_stock})"
                
                # Display medication name + manufacturer + strength
                choice_text = f"{med.name} ({med.manufacturer}) - {med.strength}{stock_info}"
                choices.append((med.id, choice_text))
            
            self.fields['clinic_medication'].choices = choices
            self.fields['patient'].queryset = Patient.objects.filter(clinic=self.clinic)


    def clean(self):
        cleaned_data = super().clean()
        clinic_medication = cleaned_data.get('clinic_medication')
        custom_medication = cleaned_data.get('custom_medication')

        if not clinic_medication and not custom_medication:
            raise forms.ValidationError("Please select a medication from inventory or enter a custom medication name.")
        if clinic_medication and custom_medication:
            raise forms.ValidationError("Please select either clinic medication OR enter custom medication, not both.")
        if clinic_medication:
            quantity = cleaned_data.get('quantity_prescribed', 1)
            if clinic_medication.quantity_in_stock < quantity:
                raise forms.ValidationError(
                    f"Insufficient stock. Available: {clinic_medication.quantity_in_stock}, "
                    f"Requested: {quantity}"
                )
        return cleaned_data


class MedicationCategoryForm(forms.ModelForm):
    class Meta:
        model = MedicationCategory
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class BulkStockUploadForm(forms.Form):
    """Form for bulk uploading stock via CSV"""
    csv_file = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv'}),
        help_text="Upload a CSV file with columns: name, strength, quantity, cost_price, selling_price, expiry_date"
    )
    overwrite_existing = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Check to update existing medications with new data"
    )
    
    


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
        
        



        
        
