from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import CustomUser, Patient
from .models import (
    DentalAppointment,
    DentalExam,
    DentalFollowUp,
    DentalMedicalRecord,
    DentalProcedure,
    DentalTreatmentPlan,
)


BASE_INPUT = 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500'


class DentalAppointmentForm(forms.ModelForm):
    class Meta:
        model = DentalAppointment
        fields = [
            'patient', 'provider', 'visit_type', 'payment_type', 'date',
            'start_time', 'end_time', 'chief_complaint', 'notes',
        ]
        widgets = {
            'patient': forms.Select(attrs={'class': BASE_INPUT}),
            'provider': forms.Select(attrs={'class': BASE_INPUT}),
            'visit_type': forms.Select(attrs={'class': BASE_INPUT}),
            'payment_type': forms.RadioSelect(),
            'date': forms.DateInput(attrs={'type': 'date', 'class': BASE_INPUT}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': BASE_INPUT}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': BASE_INPUT}),
            'chief_complaint': forms.Textarea(attrs={'rows': 3, 'class': BASE_INPUT}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': BASE_INPUT}),
        }

    def __init__(self, *args, **kwargs):
        clinic_id = kwargs.pop('clinic_id', None)
        super().__init__(*args, **kwargs)
        if clinic_id:
            self.fields['patient'].queryset = Patient.objects.filter(clinic_id=clinic_id)
            self.fields['provider'].queryset = CustomUser.objects.filter(
                clinic__id=clinic_id,
                is_active=True,
                role__in=['DENTIST', 'ADMIN'],
            ).distinct()
            self.fields['provider'].label_from_instance = lambda user: user.display_name
        else:
            self.fields['patient'].queryset = Patient.objects.none()
            self.fields['provider'].queryset = CustomUser.objects.none()

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get('date')
        start = cleaned.get('start_time')
        end = cleaned.get('end_time')
        provider = cleaned.get('provider')

        if date and date < timezone.localdate():
            raise ValidationError('Appointment date cannot be in the past.')
        if start and end and start >= end:
            raise ValidationError('End time must be after start time.')
        if provider and date and start and end:
            conflict = DentalAppointment.objects.filter(
                provider=provider,
                date=date,
                start_time__lt=end,
                end_time__gt=start,
                status__in=['SCHEDULED', 'CHECKED_IN', 'IN_CHAIR'],
            ).exclude(pk=self.instance.pk if self.instance else None)
            if conflict.exists():
                raise ValidationError('This dentist already has an appointment during that time.')
        return cleaned


class DentalExamForm(forms.ModelForm):
    tooth_chart_json = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 4, 'class': BASE_INPUT, 'placeholder': '{"11": "caries", "36": "missing"}'}),
        help_text='Optional structured tooth chart JSON. Leave blank if using notes only.',
    )

    class Meta:
        model = DentalExam
        fields = [
            'chief_complaint', 'medical_alerts', 'extraoral_exam', 'intraoral_exam',
            'periodontal_findings', 'occlusion', 'diagnosis', 'treatment_recommendation',
        ]
        widgets = {
            'chief_complaint': forms.Textarea(attrs={'rows': 3, 'class': BASE_INPUT}),
            'medical_alerts': forms.Textarea(attrs={'rows': 2, 'class': BASE_INPUT}),
            'extraoral_exam': forms.Textarea(attrs={'rows': 2, 'class': BASE_INPUT}),
            'intraoral_exam': forms.Textarea(attrs={'rows': 3, 'class': BASE_INPUT}),
            'periodontal_findings': forms.Textarea(attrs={'rows': 3, 'class': BASE_INPUT}),
            'occlusion': forms.Select(attrs={'class': BASE_INPUT}),
            'diagnosis': forms.Textarea(attrs={'rows': 3, 'class': BASE_INPUT}),
            'treatment_recommendation': forms.Textarea(attrs={'rows': 3, 'class': BASE_INPUT}),
        }

    def clean_tooth_chart_json(self):
        import json

        value = self.cleaned_data.get('tooth_chart_json', '').strip()
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError(f'Invalid JSON tooth chart: {exc.msg}')
        if not isinstance(parsed, dict):
            raise ValidationError('Tooth chart must be a JSON object.')
        return parsed


class DentalTreatmentPlanForm(forms.ModelForm):
    class Meta:
        model = DentalTreatmentPlan
        fields = ['exam', 'title', 'diagnosis', 'proposed_treatment', 'priority', 'status', 'consent_obtained', 'consent_notes']
        widgets = {
            'exam': forms.Select(attrs={'class': BASE_INPUT}),
            'title': forms.TextInput(attrs={'class': BASE_INPUT}),
            'diagnosis': forms.Textarea(attrs={'rows': 3, 'class': BASE_INPUT}),
            'proposed_treatment': forms.Textarea(attrs={'rows': 4, 'class': BASE_INPUT}),
            'priority': forms.Select(attrs={'class': BASE_INPUT}),
            'status': forms.Select(attrs={'class': BASE_INPUT}),
            'consent_notes': forms.Textarea(attrs={'rows': 2, 'class': BASE_INPUT}),
        }

    def __init__(self, *args, **kwargs):
        patient = kwargs.pop('patient', None)
        super().__init__(*args, **kwargs)
        if patient:
            self.fields['exam'].queryset = DentalExam.objects.filter(patient=patient)


class DentalProcedureForm(forms.ModelForm):
    class Meta:
        model = DentalProcedure
        fields = ['appointment', 'treatment_plan', 'tooth_numbers', 'procedure_name', 'materials_used', 'anesthesia', 'notes', 'status', 'performed_at']
        widgets = {
            'appointment': forms.Select(attrs={'class': BASE_INPUT}),
            'treatment_plan': forms.Select(attrs={'class': BASE_INPUT}),
            'tooth_numbers': forms.TextInput(attrs={'class': BASE_INPUT}),
            'procedure_name': forms.TextInput(attrs={'class': BASE_INPUT}),
            'materials_used': forms.Textarea(attrs={'rows': 2, 'class': BASE_INPUT}),
            'anesthesia': forms.TextInput(attrs={'class': BASE_INPUT}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': BASE_INPUT}),
            'status': forms.Select(attrs={'class': BASE_INPUT}),
            'performed_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': BASE_INPUT}),
        }

    def __init__(self, *args, **kwargs):
        patient = kwargs.pop('patient', None)
        super().__init__(*args, **kwargs)
        if patient:
            self.fields['appointment'].queryset = DentalAppointment.objects.filter(patient=patient)
            self.fields['treatment_plan'].queryset = DentalTreatmentPlan.objects.filter(patient=patient)


class DentalFollowUpForm(forms.ModelForm):
    class Meta:
        model = DentalFollowUp
        fields = ['provider', 'reason', 'scheduled_date', 'scheduled_time', 'notes']
        widgets = {
            'provider': forms.Select(attrs={'class': BASE_INPUT}),
            'reason': forms.Textarea(attrs={'rows': 3, 'class': BASE_INPUT}),
            'scheduled_date': forms.DateInput(attrs={'type': 'date', 'class': BASE_INPUT}),
            'scheduled_time': forms.TimeInput(attrs={'type': 'time', 'class': BASE_INPUT}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': BASE_INPUT}),
        }

    def __init__(self, *args, **kwargs):
        clinic = kwargs.pop('clinic', None)
        super().__init__(*args, **kwargs)
        if clinic:
            self.fields['provider'].queryset = CustomUser.objects.filter(
                clinic=clinic,
                is_active=True,
                role__in=['ADMIN', 'DENTIST'],
            ).distinct().order_by('first_name', 'last_name', 'username')
        else:
            self.fields['provider'].queryset = CustomUser.objects.none()
        self.fields['provider'].required = True
        self.fields['provider'].empty_label = '--------'


class DentalFollowUpClinicalForm(forms.ModelForm):
    class Meta:
        model = DentalFollowUp
        fields = ['provider', 'treatment_plan', 'reason', 'scheduled_date', 'scheduled_time', 'notes', 'completed']
        widgets = {
            'provider': forms.Select(attrs={'class': BASE_INPUT}),
            'treatment_plan': forms.Select(attrs={'class': BASE_INPUT}),
            'reason': forms.Textarea(attrs={'rows': 3, 'class': BASE_INPUT}),
            'scheduled_date': forms.DateInput(attrs={'type': 'date', 'class': BASE_INPUT}),
            'scheduled_time': forms.TimeInput(attrs={'type': 'time', 'class': BASE_INPUT}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': BASE_INPUT}),
        }

    def __init__(self, *args, **kwargs):
        patient = kwargs.pop('patient', None)
        clinic = kwargs.pop('clinic', None)
        super().__init__(*args, **kwargs)
        clinic = clinic or getattr(patient, 'clinic', None)
        if clinic:
            self.fields['provider'].queryset = CustomUser.objects.filter(
                clinic=clinic,
                is_active=True,
                role__in=['ADMIN', 'DENTIST'],
            ).distinct().order_by('first_name', 'last_name', 'username')
        else:
            self.fields['provider'].queryset = CustomUser.objects.none()
        self.fields['provider'].required = True
        self.fields['provider'].empty_label = '--------'
        if patient:
            self.fields['treatment_plan'].queryset = DentalTreatmentPlan.objects.filter(patient=patient)


class DentalMedicalRecordForm(forms.ModelForm):
    class Meta:
        model = DentalMedicalRecord
        fields = ['record_type', 'title', 'description']
        widgets = {
            'record_type': forms.Select(attrs={'class': BASE_INPUT}),
            'title': forms.TextInput(attrs={'class': BASE_INPUT}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': BASE_INPUT}),
        }
