from django import forms
from django.http import QueryDict
from core.models import Patient, CustomUser, ServicePriceList
from django.utils import timezone
from .models import (EyeAppointment, EyeMedicalRecord, EyeFollowUp, EyeExam,
                     OpticalProduct, OpticalDispense, OpticalPrescriptionRequest)
from django.core.exceptions import ValidationError




# Add this import at the top
from django.utils.html import format_html

# Modify the EyeAppointmentForm class
class EyeAppointmentForm(forms.ModelForm):
    date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    start_time = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}))
    end_time = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}))
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))
    # Change payment_type to use RadioSelect explicitly
    payment_type = forms.ChoiceField(
        choices=EyeAppointment.PAYMENT_CHOICES, 
        required=True,
        widget=forms.RadioSelect
    )

    class Meta:
        model = EyeAppointment
        fields = ['patient', 'provider', 'date', 'start_time', 'end_time', 'reason', 'notes', 'payment_type']
        
    def __init__(self, *args, **kwargs):
        clinic_id = kwargs.pop('clinic_id', None)
        self.clinic_id = clinic_id
        instance = kwargs.get('instance')
        self._original_date = instance.date if instance and instance.pk else None
        super().__init__(*args, **kwargs)

        # Filter providers by clinic (ManyToMany)
        if clinic_id:
            self.fields['patient'].queryset = Patient.objects.filter(clinic_id=clinic_id).order_by('first_name', 'last_name')
            self.fields['provider'].queryset = CustomUser.objects.filter(
                clinic__id=clinic_id,
                is_active=True,
                role__in=['ADMIN', 'DOCTOR', 'OPTOMETRIST', 'RECEPTIONIST', 'NURSE'],
            ).distinct().order_by('first_name', 'last_name', 'username')
        else:
            self.fields['patient'].queryset = Patient.objects.none()
            self.fields['provider'].queryset = CustomUser.objects.none()

        # Format patient names as "Name (Patient ID) + DOB"
        self.fields['patient'].label_from_instance = lambda obj: format_html(
            "{} ({}) - DOB: {}", 
            obj.full_name, 
            obj.patient_id,
            obj.date_of_birth.strftime('%Y-%m-%d') if obj.date_of_birth else 'N/A'
        )
        
        # Show full name + title for providers
        self.fields['provider'].label_from_instance = lambda obj: f"{obj.title or ''} {obj.get_full_name()}"

        # Add styling and placeholder
        self.fields['provider'].widget.attrs.update({
            'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md'
        })
        self.fields['provider'].empty_label = "--------"
    
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
            overlapping = EyeAppointment.objects.filter(
                clinic_id=self.clinic_id,
                provider=provider,
                date=date,
                start_time__lt=end_time,
                end_time__gt=start_time
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if overlapping.exists():
                raise ValidationError("This provider already has an appointment scheduled during this time.")

        patient = cleaned_data.get('patient')
        if self.clinic_id and patient and patient.clinic_id != int(self.clinic_id):
            raise ValidationError("Selected patient does not belong to the active clinic.")
        if self.clinic_id and provider and not provider.clinic.filter(id=self.clinic_id).exists():
            raise ValidationError("Selected provider does not belong to the active clinic.")

        return cleaned_data
       


            
            

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
    optical_services = forms.ModelMultipleChoiceField(
        queryset=ServicePriceList.objects.none(),
        required=False,
        label='Services and Optical',
        widget=forms.SelectMultiple(attrs={'class': 'js-optical-services w-full', 'data-placeholder': 'Select services and optical'}),
    )

    class Meta:
        model = EyeExam
        fields = [
            'appointment',
            'chief_complaint',
            'ocular_history',
            'systemic_risk_factors',
            'ocular_medications',
            'eye_allergies',
            'visual_acuity_right',
            'visual_acuity_left',
            'visual_acuity_right_corrected',
            'visual_acuity_left_corrected',
            'pinhole_right',
            'pinhole_left',
            'near_vision_right',
            'near_vision_left',
            'intraocular_pressure_right',
            'intraocular_pressure_left',
            'anterior_segment_findings',
            'slit_lamp_findings',
            'lens_findings',
            'posterior_segment_findings',
            'fundus_exam_findings',
            'retina_findings',
            'optic_disc_findings',
            'refraction_right',
            'refraction_left',
            'objective_refraction_right',
            'objective_refraction_left',
            'final_prescription_right',
            'final_prescription_left',
            'pupillary_distance',
            # Standard eye-exam extensions
            'pupils_perrla', 'rapd_note',
            'extraocular_motility', 'cover_test',
            'confrontation_visual_fields', 'colour_vision',
            'iop_method', 'iop_time',
            'cup_disc_ratio_right', 'cup_disc_ratio_left',
            'keratometry_right', 'keratometry_left',
            'pachymetry_right', 'pachymetry_left',
            'prism_right', 'prism_left',
            'base_direction_right', 'base_direction_left',
            'diagnosis',
            'treatment_plan',
            'procedure_notes',
            'imaging_results',
            'spectacle_or_contact_lens_plan',
            'optical_services',
            'optician_order',
            'follow_up_plan',
            'notes',
            'sphere_right', 'cylinder_right', 'axis_right', 'add_right', 'pupil_size_right',
            'sphere_left', 'cylinder_left', 'axis_left', 'add_left', 'pupil_size_left',
        ]
        widgets = {
            'appointment': forms.Select(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'chief_complaint': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'ocular_history': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'systemic_risk_factors': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'ocular_medications': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'eye_allergies': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'visual_acuity_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'visual_acuity_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'visual_acuity_right_corrected': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'visual_acuity_left_corrected': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'pinhole_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'pinhole_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'near_vision_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'near_vision_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'intraocular_pressure_right': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'intraocular_pressure_left': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'anterior_segment_findings': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'slit_lamp_findings': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'lens_findings': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'posterior_segment_findings': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'fundus_exam_findings': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'retina_findings': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'optic_disc_findings': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'refraction_right': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'refraction_left': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'objective_refraction_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'objective_refraction_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'final_prescription_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'final_prescription_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'pupillary_distance': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'pupils_perrla': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. PERRLA'}),
            'rapd_note': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'RAPD (e.g. none / +OS)'}),
            'extraocular_motility': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. Full OU'}),
            'cover_test': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. Orthophoric'}),
            'confrontation_visual_fields': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. Full to confrontation OU'}),
            'colour_vision': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. Ishihara 14/14'}),
            'iop_method': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'Goldmann / NCT / Tono-pen'}),
            'iop_time': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. 10:30'}),
            'cup_disc_ratio_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. 0.3'}),
            'cup_disc_ratio_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. 0.3'}),
            'keratometry_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. 43.00/44.00 @ 90'}),
            'keratometry_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. 43.00/44.00 @ 90'}),
            'pachymetry_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. 545 µm'}),
            'pachymetry_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. 545 µm'}),
            'prism_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. 2Δ'}),
            'prism_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'e.g. 2Δ'}),
            'base_direction_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'Base direction (BU/BD/BI/BO)'}),
            'base_direction_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'Base direction (BU/BD/BI/BO)'}),
            'diagnosis': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'treatment_plan': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'procedure_notes': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'imaging_results': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'spectacle_or_contact_lens_plan': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'frame_prescribed': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-blue-600 border-gray-300 rounded'}),
            'frame_product': forms.Select(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'frame_prescription': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'Frame type, model, colour, size, or fitting notes'}),
            'lens_prescribed': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-blue-600 border-gray-300 rounded'}),
            'lens_product': forms.Select(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'lens_prescription': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'Lens type, coating, tint, material, or prescription notes'}),
            'optician_order': forms.Textarea(attrs={'rows': 4, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg', 'placeholder': 'Manual optician job order or instruction, e.g. lens transfer'}),
            'follow_up_plan': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'sphere_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'cylinder_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'axis_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'add_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'pupil_size_right': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'sphere_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'cylinder_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'axis_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'add_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
            'pupil_size_left': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg'}),
        }

    def __init__(self, *args, **kwargs):
        clinic_id = kwargs.pop('clinic_id', None)
        self.clinic_id = clinic_id
        if args:
            args = (self._normalized_data(args[0], clinic_id), *args[1:])
        super().__init__(*args, **kwargs)
        if clinic_id:
            self.fields['optical_services'].queryset = ServicePriceList.objects.filter(
                clinic_id=clinic_id,
                is_active=True,
            ).order_by('name')
        else:
            self.fields['optical_services'].queryset = ServicePriceList.objects.none()
        self.fields['optical_services'].label_from_instance = lambda obj: obj.name

    @staticmethod
    def _normalized_data(data, clinic_id):
        if hasattr(data, 'getlist'):
            values = data.getlist('optical_services')
        elif isinstance(data, dict):
            raw_values = data.get('optical_services')
            values = raw_values if isinstance(raw_values, list) else [raw_values] if raw_values else []
        else:
            return data

        if not values:
            return data

        normalized = []
        service_sync_ids = []
        for value in values:
            text = str(value)
            if text.isdigit():
                normalized.append(text)
                continue
            if ':service:' in text:
                service_sync_ids.append(text.rsplit(':service:', 1)[1])

        if service_sync_ids and clinic_id:
            normalized.extend(
                str(pk)
                for pk in ServicePriceList.objects.filter(
                    clinic_id=clinic_id,
                    sync_id__in=service_sync_ids,
                ).values_list('pk', flat=True)
            )

        if len(normalized) == len(values):
            return data

        next_data = data.copy() if isinstance(data, QueryDict) else data.copy()
        if hasattr(next_data, 'setlist'):
            next_data.setlist('optical_services', normalized)
        else:
            next_data['optical_services'] = normalized
        return next_data

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
            if not cleaned_data.get(field):
                cleaned_data[field] = default_value
        return cleaned_data


OPTICAL_INPUT_CLASS = 'w-full px-3 py-2 border-2 border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent'


class OpticalProductForm(forms.ModelForm):
    class Meta:
        model = OpticalProduct
        fields = [
            'product_type', 'name', 'brand', 'model_code', 'colour', 'size',
            'material', 'sphere', 'cylinder', 'axis',
            'quantity_in_stock', 'minimum_stock_level', 'cost_price', 'selling_price',
            'status', 'batch_number', 'expiry_date',
        ]
        widgets = {
            'product_type': forms.Select(attrs={'class': OPTICAL_INPUT_CLASS}),
            'name': forms.TextInput(attrs={'class': OPTICAL_INPUT_CLASS, 'placeholder': 'Product name'}),
            'brand': forms.TextInput(attrs={'class': OPTICAL_INPUT_CLASS, 'placeholder': 'Brand (optional)'}),
            'model_code': forms.TextInput(attrs={'class': OPTICAL_INPUT_CLASS, 'placeholder': 'Model / SKU'}),
            'colour': forms.TextInput(attrs={'class': OPTICAL_INPUT_CLASS, 'placeholder': 'Colour'}),
            'size': forms.TextInput(attrs={'class': OPTICAL_INPUT_CLASS, 'placeholder': 'Size (e.g. 52-18-140)'}),
            'material': forms.TextInput(attrs={'class': OPTICAL_INPUT_CLASS, 'placeholder': 'Material'}),
            'sphere': forms.TextInput(attrs={'class': OPTICAL_INPUT_CLASS, 'placeholder': 'Sphere (stock lens)'}),
            'cylinder': forms.TextInput(attrs={'class': OPTICAL_INPUT_CLASS, 'placeholder': 'Cylinder (stock lens)'}),
            'axis': forms.TextInput(attrs={'class': OPTICAL_INPUT_CLASS, 'placeholder': 'Axis (stock lens)'}),
            'quantity_in_stock': forms.NumberInput(attrs={'class': OPTICAL_INPUT_CLASS, 'min': '0'}),
            'minimum_stock_level': forms.NumberInput(attrs={'class': OPTICAL_INPUT_CLASS, 'min': '0'}),
            'cost_price': forms.NumberInput(attrs={'class': OPTICAL_INPUT_CLASS, 'step': '0.01', 'min': '0'}),
            'selling_price': forms.NumberInput(attrs={'class': OPTICAL_INPUT_CLASS, 'step': '0.01', 'min': '0'}),
            'status': forms.Select(attrs={'class': OPTICAL_INPUT_CLASS}),
            'batch_number': forms.TextInput(attrs={'class': OPTICAL_INPUT_CLASS, 'placeholder': 'Batch/Lot number'}),
            'expiry_date': forms.DateInput(attrs={'class': OPTICAL_INPUT_CLASS, 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        # Accept an optional clinic kwarg for parity with the pharmacy form.
        self.clinic = kwargs.pop('clinic', None)
        super().__init__(*args, **kwargs)


class OpticalDispenseForm(forms.ModelForm):
    class Meta:
        model = OpticalDispense
        fields = ['patient', 'quantity', 'notes']
        widgets = {
            'patient': forms.Select(attrs={'class': OPTICAL_INPUT_CLASS}),
            'quantity': forms.NumberInput(attrs={'class': OPTICAL_INPUT_CLASS, 'min': '1', 'value': '1'}),
            'notes': forms.Textarea(attrs={'class': OPTICAL_INPUT_CLASS, 'rows': 2, 'placeholder': 'Notes (optional)'}),
        }

    def __init__(self, *args, **kwargs):
        clinic_id = kwargs.pop('clinic_id', None)
        self.product = kwargs.pop('product', None)
        super().__init__(*args, **kwargs)
        self.fields['quantity'].min_value = 1
        if clinic_id:
            self.fields['patient'].queryset = Patient.objects.filter(
                clinic_id=clinic_id, clinic__clinic_type='EYE'
            ).order_by('first_name', 'last_name')
        self.fields['patient'].empty_label = 'Select patient'

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity') or 0
        if quantity < 1:
            raise ValidationError('Quantity must be at least 1.')
        if self.product and quantity > self.product.quantity_in_stock:
            raise ValidationError(
                f'Only {self.product.quantity_in_stock} in stock for {self.product.display_name}.'
            )
        return quantity


class OpticalPrescriptionRequestNoteForm(forms.ModelForm):
    class Meta:
        model = OpticalPrescriptionRequest
        fields = ['optician_note']
        widgets = {
            'optician_note': forms.Textarea(attrs={
                'class': OPTICAL_INPUT_CLASS,
                'rows': 3,
                'placeholder': 'Custom lens/frame notes, lab order details, supplier reference, or fitting instructions',
            }),
        }
