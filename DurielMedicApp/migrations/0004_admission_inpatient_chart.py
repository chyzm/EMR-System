import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('DurielMedicApp', '0003_offline_sync_ids'),
        ('core', '0004_prescription_sync_id'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='admission',
            name='admission_source',
            field=models.CharField(choices=[('OPD', 'Outpatient Department'), ('EMERGENCY', 'Emergency Unit'), ('REFERRAL', 'Referral'), ('TRANSFER', 'Transfer'), ('DIRECT', 'Direct Admission')], default='OPD', max_length=20),
        ),
        migrations.AddField(
            model_name='admission',
            name='admission_type',
            field=models.CharField(choices=[('EMERGENCY', 'Emergency'), ('ELECTIVE', 'Elective'), ('REFERRAL', 'Referral'), ('OBSERVATION', 'Observation'), ('MATERNITY', 'Maternity'), ('SURGICAL', 'Surgical')], default='EMERGENCY', max_length=20),
        ),
        migrations.AddField(
            model_name='admission',
            name='attending_doctor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='admissions_attending', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='admission',
            name='bed',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='admission',
            name='discharge_condition',
            field=models.CharField(blank=True, choices=[('STABLE', 'Stable'), ('IMPROVED', 'Improved'), ('UNCHANGED', 'Unchanged'), ('CRITICAL', 'Critical'), ('REFERRED', 'Referred'), ('DECEASED', 'Deceased')], max_length=20),
        ),
        migrations.AddField(
            model_name='admission',
            name='discharge_diagnosis',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='admission',
            name='discharge_instructions',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='admission',
            name='discharge_summary',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='admission',
            name='expected_discharge_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='admission',
            name='follow_up_plan',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='admission',
            name='provisional_diagnosis',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='admission',
            name='status',
            field=models.CharField(choices=[('ADMITTED', 'Admitted'), ('TRANSFERRED', 'Transferred'), ('DISCHARGED', 'Discharged'), ('REFERRED', 'Referred'), ('DECEASED', 'Deceased'), ('DAMA', 'Discharged Against Medical Advice')], default='ADMITTED', max_length=20),
        ),
        migrations.CreateModel(
            name='MedicationAdministration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sync_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('medication_name', models.CharField(max_length=200)),
                ('dose', models.CharField(max_length=100)),
                ('route', models.CharField(blank=True, max_length=50)),
                ('scheduled_time', models.DateTimeField(blank=True, null=True)),
                ('administered_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('status', models.CharField(choices=[('GIVEN', 'Given'), ('HELD', 'Held'), ('REFUSED', 'Refused'), ('MISSED', 'Missed')], default='GIVEN', max_length=12)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('administered_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('admission', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='medication_administrations', to='DurielMedicApp.admission')),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='medication_administrations', to='core.patient')),
                ('prescription', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='administrations', to='core.prescription')),
            ],
            options={
                'ordering': ['-administered_at'],
                'indexes': [
                    models.Index(fields=['admission', '-administered_at'], name='DurielMedic_med_adm_idx'),
                    models.Index(fields=['patient', '-administered_at'], name='DurielMedic_med_pat_idx'),
                ],
            },
        ),
    ]
