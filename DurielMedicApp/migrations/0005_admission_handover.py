import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('DurielMedicApp', '0004_admission_inpatient_chart'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AdmissionHandover',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sync_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('handover_type', models.CharField(choices=[('DOCTOR', 'Doctor Handover'), ('NURSE', 'Nurse Handover'), ('SHIFT', 'Shift Handover'), ('TRANSFER', 'Transfer Handover')], default='SHIFT', max_length=20)),
                ('summary', models.TextField()),
                ('current_condition', models.TextField(blank=True)),
                ('pending_tasks', models.TextField(blank=True)),
                ('concerns', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('admission', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='handovers', to='DurielMedicApp.admission')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='admission_handovers_given', to=settings.AUTH_USER_MODEL)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='admission_handovers', to='core.patient')),
                ('receiving_staff', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='admission_handovers_received', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['admission', '-created_at'], name='DurielMedic_handov_adm_idx'),
                    models.Index(fields=['patient', '-created_at'], name='DurielMedic_handov_pat_idx'),
                ],
            },
        ),
    ]
