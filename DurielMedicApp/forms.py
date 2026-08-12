from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Sum
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column
from core.models import CustomUser, Patient, Prescription
from .models import Appointment, MedicalRecord, Vitals, Admission, FollowUp, PhysiotherapyRecord, PhysiotherapyReferral, MedicationAdministration, AdmissionHandover

class VitalsForm(forms.ModelForm):
    class Meta:
        model = Vitals
        fields = [
            'blood_pressure', 'pulse', 'temperature', 'weight',
            'respiratory_rate', 'oxygen_saturation', 'height', 'bmi',
            'category', 'notes',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200'
            }),
            'temperature': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200',
                'step': '0.1'
            }),
            'blood_pressure_systolic': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200'
            }),
            'blood_pressure_diastolic': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200'
            }),
            'pulse': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200'
            }),
            'respiratory_rate': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200'
            }),
            'oxygen_saturation': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200',
                'min': '0',
                'max': '100'
            }),
            'height': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200',
                'step': '0.1'
            }),
            'weight': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200',
                'step': '0.1'
            }),
            'bmi': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200',
                'readonly': 'readonly',
                'step': '0.1'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add common classes to all visible fields automatically
        for field_name, field in self.fields.items():
            if field_name != 'appointment' and not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs.update({
                    'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200'
                })

class FollowUpForm(forms.ModelForm):
    class Meta:
        model = FollowUp
        fields = ['reason', 'scheduled_date', 'scheduled_time', 'notes']
        widgets = {
            'scheduled_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'scheduled_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

class AdmissionForm(forms.ModelForm):
    class Meta:
        model = Admission
        fields = [
            'ward',
            'bed',
            'admission_type',
            'admission_source',
            'attending_doctor',
            'provisional_diagnosis',
            'reason',
            'expected_discharge_date',
        ]
        widgets = {
            'ward': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition duration-200',
                'placeholder': 'e.g., Ward A'
            }),
            'bed': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition duration-200',
                'placeholder': 'e.g., Bed 12'
            }),
            'admission_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition duration-200',
            }),
            'admission_source': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition duration-200',
            }),
            'attending_doctor': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition duration-200',
            }),
            'provisional_diagnosis': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition duration-200',
                'placeholder': 'Provisional diagnosis...'
            }),
            'reason': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition duration-200 h-32',
                'placeholder': 'Reason for admission...'
            }),
            'expected_discharge_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition duration-200',
            }),
        }

    def __init__(self, *args, **kwargs):
        clinic = kwargs.pop('clinic', None)
        super().__init__(*args, **kwargs)
        if clinic:
            from django.contrib.auth import get_user_model
            self.fields['attending_doctor'].queryset = get_user_model().objects.filter(
                clinic=clinic,
                is_active=True,
                role__in=['DOCTOR', 'OPTOMETRIST', 'PHYSIOTHERAPIST'],
            ).distinct()


class DischargeForm(forms.ModelForm):
    class Meta:
        model = Admission
        fields = [
            'discharge_diagnosis',
            'discharge_condition',
            'discharge_summary',
            'discharge_instructions',
            'follow_up_plan',
        ]
        widgets = {
            'discharge_diagnosis': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'Final diagnosis...'}),
            'discharge_condition': forms.Select(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'discharge_summary': forms.Textarea(attrs={'rows': 4, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'Clinical course and summary...'}),
            'discharge_instructions': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'Medication, wound care, warning signs...'}),
            'follow_up_plan': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'Follow-up clinic/date plan...'}),
        }


class MedicationAdministrationForm(forms.ModelForm):
    class Meta:
        model = MedicationAdministration
        fields = [
            'prescription',
            'quantity_administered',
            'route',
            'scheduled_time',
            'administered_at',
            'status',
            'notes',
        ]
        widgets = {
            'prescription': forms.Select(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'quantity_administered': forms.NumberInput(attrs={'min': 1, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'route': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g., Oral, IV, IM'}),
            'scheduled_time': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'administered_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'status': forms.Select(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'Administration notes...'}),
        }

    def __init__(self, *args, **kwargs):
        self.admission = kwargs.pop('admission', None)
        super().__init__(*args, **kwargs)
        if self.admission:
            self.fields['prescription'].queryset = Prescription.objects.filter(
                patient=self.admission.patient,
                clinic=self.admission.clinic,
                is_active=True,
                clinic_medication__isnull=False,
            ).order_by('-date_prescribed')

    def clean(self):
        cleaned_data = super().clean()
        prescription = cleaned_data.get('prescription')
        quantity = cleaned_data.get('quantity_administered') or 0
        if not prescription:
            raise ValidationError('Select an active prescription before recording administration.')
        if not self.admission or (
            prescription.patient_id != self.admission.patient_id
            or prescription.clinic_id != self.admission.clinic_id
        ):
            raise ValidationError('This prescription does not belong to the admitted patient.')
        if not prescription.is_active:
            raise ValidationError('This prescription has been deactivated and cannot be administered.')
        if not prescription.clinic_medication_id:
            raise ValidationError('Only medication supplied by the clinic pharmacy can be administered.')
        already_given = prescription.administrations.filter(status='GIVEN').exclude(
            pk=self.instance.pk,
        ).aggregate(total=Sum('quantity_administered'))['total'] or 0
        if quantity < 1:
            self.add_error('quantity_administered', 'Enter at least one unit.')
        elif already_given + quantity > prescription.quantity_prescribed:
            self.add_error(
                'quantity_administered',
                f'Only {max(prescription.quantity_prescribed - already_given, 0)} unit(s) remain on this prescription.',
            )
        return cleaned_data


class AdmissionHandoverForm(forms.ModelForm):
    class Meta:
        model = AdmissionHandover
        fields = [
            'handover_type',
            'receiving_staff',
            'summary',
            'current_condition',
            'pending_tasks',
            'concerns',
        ]
        widgets = {
            'handover_type': forms.Select(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'receiving_staff': forms.Select(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'summary': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'current_condition': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'pending_tasks': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'concerns': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
        }

    def __init__(self, *args, **kwargs):
        clinic = kwargs.pop('clinic', None)
        super().__init__(*args, **kwargs)
        if clinic:
            from django.contrib.auth import get_user_model
            self.fields['receiving_staff'].queryset = get_user_model().objects.filter(
                clinic=clinic,
                is_active=True,
                role__in=['DOCTOR', 'NURSE'],
            ).distinct()

# class AppointmentForm(forms.ModelForm):
#     class Meta:
#         model = Appointment
#         payment_type = forms.ChoiceField(choices=Appointment.PAYMENT_CHOICES, required=True)
#         fields = ['patient', 'provider', 'date', 'start_time', 'end_time', 'reason', 'notes', 'payment_type']
#         widgets = {
#             'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
#             'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
#             'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
#             'reason': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
#             'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
#             'payment_type': forms.RadioSelect(choices=Appointment.PAYMENT_CHOICES),
#         }
    
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.fields['provider'].label_from_instance = lambda obj: f"{obj.title or ''} {obj.get_full_name()}"
#         self.fields['provider'].widget.attrs.update({
#             'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md'
#         })
#         # Add empty label to force blank initial option
#         self.fields['provider'].empty_label = "--------"
#         # Remove any initial value so dropdown starts blank
#         self.initial['provider'] = None



# Add this import at the top
from django.utils.html import format_html

# Modify the AppointmentForm class
class AppointmentForm(forms.ModelForm):
    # Add payment_type field explicitly
    payment_type = forms.ChoiceField(
        choices=Appointment.PAYMENT_CHOICES, 
        required=True,
        widget=forms.RadioSelect
    )
    
    class Meta:
        model = Appointment
        fields = ['patient', 'provider', 'date', 'start_time', 'end_time', 'reason', 'notes', 'payment_type']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        clinic_id = kwargs.pop('clinic_id', None)
        instance = kwargs.get('instance')
        self._original_date = instance.date if instance and instance.pk else None
        super().__init__(*args, **kwargs)

        if clinic_id:
            self.fields['patient'].queryset = Patient.objects.filter(clinic_id=clinic_id).order_by('first_name', 'last_name')
            self.fields['provider'].queryset = CustomUser.objects.filter(
                clinic__id=clinic_id,
                is_active=True,
                role__in=['ADMIN', 'DOCTOR', 'RECEPTIONIST', 'NURSE', 'PHYSIOTHERAPIST'],
            ).distinct().order_by('first_name', 'last_name', 'username')
        
        # Format patient names as "Name (Patient ID) + DOB"
        self.fields['patient'].label_from_instance = lambda obj: format_html(
            "{} ({}) - DOB: {}", 
            obj.full_name, 
            obj.patient_id,
            obj.date_of_birth.strftime('%Y-%m-%d') if obj.date_of_birth else 'N/A'
        )
        
        # Format provider names
        self.fields['provider'].label_from_instance = lambda obj: f"{obj.title or ''} {obj.get_full_name()}"
        
        # Update provider widget attributes
        self.fields['provider'].widget.attrs.update({
            'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md'
        })
        
        # Add empty label to force blank initial option
        self.fields['provider'].empty_label = "--------"
        # Never clear the existing provider while editing. Doing so made a
        # normal edit silently fail validation unless staff reselected it.


    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get('date')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        provider = cleaned_data.get('provider')
        
        if date and date < timezone.localdate() and date != self._original_date:
            raise ValidationError("Appointment date cannot be in the past.")
        
        if start_time and end_time and start_time >= end_time:
            raise ValidationError("End time must be after start time.")
        
        if provider and date and start_time and end_time:
            overlapping = Appointment.objects.filter(
                provider=provider,
                date=date,
                start_time__lt=end_time,
                end_time__gt=start_time
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if overlapping.exists():
                raise ValidationError("This provider already has an appointment scheduled during this time.")

        return cleaned_data




class MedicalRecordForm(forms.ModelForm):
    class Meta:
        model = MedicalRecord
        fields = [
            'chief_complaint',
            'history_of_present_illness',
            'past_medical_history',
            'diagnosis',
            'treatment_plan',
            'lab_results',
            'imaging_results',
            'allergies',
            'procedures',
            'additional_notes',
        ]
        widgets = {
            'chief_complaint': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter chief complaint...'}),
            'history_of_present_illness': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter history of present illness...'}),
            'past_medical_history': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter past medical history...'}),
            'diagnosis': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter diagnosis...'}),
            'treatment_plan': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter treatment plan...'}),
            'lab_results': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter lab results...'}),
            'imaging_results': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter imaging results...'}),
            'allergies': forms.Textarea(attrs={'rows': 2, 'class': 'form-control', 'placeholder': 'Enter known allergies...'}),
            'procedures': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter procedures performed...'}),
            'additional_notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter any additional notes...'}),
        }


class PhysiotherapyRecordForm(forms.ModelForm):
    session_count = forms.IntegerField(required=False, min_value=0)

    class Meta:
        model = PhysiotherapyRecord
        fields = [
            'chief_complaint',
            'history_of_present_illness',
            'past_medical_history',
            'physical_examination',
            'diagnosis',
            'treatment_goals',
            'treatment_plan',
            'exercises_prescribed',
            'modalities_used',
            'progress_notes',
            'session_count',
            'session_dates',
            'additional_notes',
        ]
        widgets = {
            'chief_complaint': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter chief complaint...'}),
            'history_of_present_illness': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter history of present illness...'}),
            'past_medical_history': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter past medical history...'}),
            'physical_examination': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter physical examination findings...'}),
            'diagnosis': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter diagnosis...'}),
            'treatment_goals': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter treatment goals...'}),
            'treatment_plan': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter treatment plan...'}),
            'exercises_prescribed': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter exercises prescribed...'}),
            'modalities_used': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter modalities used (e.g., ultrasound, TENS, heat/cold therapy)...'}),
            'progress_notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter progress notes...'}),
            'session_count': forms.NumberInput(attrs={'min': 0, 'class': 'form-control', 'placeholder': 'Number of sessions held'}),
            'session_dates': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'One session date per line, e.g. 2026-08-11'}),
            'additional_notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Enter any additional notes...'}),
        }


class PhysiotherapyReferralForm(forms.ModelForm):
    class Meta:
        model = PhysiotherapyReferral
        fields = ['assigned_to', 'priority', 'reason', 'notes']
        widgets = {
            'assigned_to': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100'}),
            'priority': forms.Select(attrs={'class': 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100'}),
            'reason': forms.Textarea(attrs={'rows': 4, 'class': 'w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100', 'placeholder': 'Reason for physiotherapy referral...'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100', 'placeholder': 'Optional handoff notes...'}),
        }

    def __init__(self, *args, **kwargs):
        clinic = kwargs.pop('clinic', None)
        super().__init__(*args, **kwargs)
        if clinic:
            self.fields['assigned_to'].queryset = CustomUser.objects.filter(
                clinic=clinic,
                is_active=True,
                role='PHYSIOTHERAPIST',
            ).distinct().order_by('first_name', 'last_name', 'username')
        self.fields['assigned_to'].label_from_instance = lambda obj: obj.get_full_name() or obj.username
        self.fields['assigned_to'].required = False
        self.fields['assigned_to'].empty_label = 'Any available physiotherapist'
