from django import forms
from core.models import Patient, CustomUser
from django.utils import timezone
from .models import (EyeAppointment, EyeMedicalRecord, EyeFollowUp, EyeExam)
from django.core.exceptions import ValidationError




class EyeAppointmentForm(forms.ModelForm):
    date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    start_time = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}))
    end_time = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}))
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))

    class Meta:
        model = EyeAppointment
        fields = ['patient', 'provider', 'date', 'start_time', 'end_time', 'reason', 'notes']

    def __init__(self, *args, **kwargs):
        clinic_id = kwargs.pop('clinic_id', None)
        super().__init__(*args, **kwargs)

        # Filter providers by clinic (ManyToMany)
        if clinic_id:
            self.fields['provider'].queryset = CustomUser.objects.filter(clinic__id=clinic_id)
        else:
            self.fields['provider'].queryset = CustomUser.objects.none()

        # Show full name + title
        self.fields['provider'].label_from_instance = lambda obj: f"{obj.title or ''} {obj.get_full_name()}"

        # Add styling and placeholder
        self.fields['provider'].widget.attrs.update({
            'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md'
        })
        self.fields['provider'].empty_label = "--------"
        self.initial['provider'] = None
    
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
        
        if provider and date and start_time and end_time:
            overlapping = EyeAppointment.objects.filter(
                provider=provider,
                date=date,
                start_time__lt=end_time,
                end_time__gt=start_time
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if overlapping.exists():
                raise ValidationError("This provider already has an appointment scheduled during this time.")

            
            

class EyeMedicalRecordForm(forms.ModelForm):
    class Meta:
        model = EyeMedicalRecord
        fields = ['record_type', 'title', 'description']


class EyeFollowUpForm(forms.ModelForm):
    scheduled_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    scheduled_time = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}))

    class Meta:
        model = EyeFollowUp
        fields = ['patient', 'reason', 'scheduled_date', 'scheduled_time', 'notes', 'completed']

    def __init__(self, *args, **kwargs):
        clinic_id = kwargs.pop('clinic_id', None)
        super().__init__(*args, **kwargs)
        if clinic_id:
            self.fields['patient'].queryset = Patient.objects.filter(clinic_id=clinic_id, clinic__clinic_type='EYE')


class EyeExamForm(forms.ModelForm):
    class Meta:
        model = EyeExam
        fields = [
            'appointment',
            'visual_acuity_right',
            'visual_acuity_left',
            'intraocular_pressure_right',
            'intraocular_pressure_left',
            'slit_lamp_findings',
            'fundus_exam_findings',
            'refraction_right',
            'refraction_left',
            'notes',
            'sphere_right', 'cylinder_right', 'axis_right', 'add_right', 'pupil_size_right',
            'sphere_left', 'cylinder_left', 'axis_left', 'add_left', 'pupil_size_left',
        ]
        widgets = {
            'slit_lamp_findings': forms.Textarea(attrs={'rows': 3}),
            'fundus_exam_findings': forms.Textarea(attrs={'rows': 3}),
            'refraction_right': forms.Textarea(attrs={'rows': 2}),
            'refraction_left': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }
        
        def clean(self):
            cleaned_data = super().clean()

            defaults = {
                'sphere_right': 'Not recorded',
                'cylinder_right': 'Not recorded',
                'axis_right': 'Not recorded',
                'add_right': 'Not recorded',
                'pupil_size_right': 'Not recorded mm',
                'sphere_left': 'Not recorded',
                'cylinder_left': 'Not recorded',
                'axis_left': 'Not recorded',
                'add_left': 'Not recorded',
                'pupil_size_left': 'Not recorded mm',
            }

            for field, default_value in defaults.items():
                if not cleaned_data.get(field):  # Empty or None
                    cleaned_data[field] = default_value

            return cleaned_data
