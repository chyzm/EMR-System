from django import forms
from core.models import Patient
from .models import (
    EyeAppointment,
    EyeMedicalRecord,
    EyeFollowUp,
    EyeExam
)


class EyeAppointmentForm(forms.ModelForm):
    date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    start_time = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}))
    end_time = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}))

    class Meta:
        model = EyeAppointment
        fields = ['patient', 'provider', 'date', 'start_time', 'end_time', 'reason', 'status', 'notes']
        
    reason = forms.CharField(required=False)  # Make optional

    # def __init__(self, *args, **kwargs):
    #     clinic_id = kwargs.pop('clinic_id', None)
    #     super().__init__(*args, **kwargs)
    #     if clinic_id:
    #         self.fields['patient'].queryset = Patient.objects.filter(clinic_id=clinic_id, clinic__clinic_type='EYE')
    
    def __init__(self, *args, **kwargs):
        clinics = kwargs.pop('clinics', None)  # get clinics from kwargs
        super().__init__(*args, **kwargs)

        if clinics:
            # Filter patients belonging to user's clinics
            self.fields['patient'].queryset = Patient.objects.filter(clinic__in=clinics)
        else:
            self.fields['patient'].queryset = Patient.objects.none()
            
            

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
