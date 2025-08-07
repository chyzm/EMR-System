from core.models import Patient
from django.db import models

class EyeExam(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, 
                              limit_choices_to={'clinic__clinic_type': 'EYE'})
    visual_acuity = models.CharField(max_length=20)
    intraocular_pressure = models.FloatField()
    # Other eye-specific fields
