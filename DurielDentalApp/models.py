from core.models import Patient
from django.db import models

class DentalExam(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE,
                               limit_choices_to={'clinic__clinic_type': 'DENTAL'})
    tooth_chart = models.JSONField()
    # Other dental-specific fields
