from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0021_add_lab_models_and_billing_discount'),
        ('DurielMedicApp', '0008_physiotherapyrecord'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='admission',
            options={'ordering': ['-date_admitted']},
        ),
        migrations.AlterField(
            model_name='admission',
            name='patient',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='admissions',
                to='core.patient',
            ),
        ),
        migrations.AddField(
            model_name='admission',
            name='clinic',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='admissions',
                to='core.clinic',
            ),
        ),
        migrations.AddField(
            model_name='admission',
            name='admitted_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='admissions_created',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='admission',
            name='discharged_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='admission',
            name='discharged_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='admissions_discharged',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name='admission',
            index=models.Index(fields=['clinic'], name='DurielMedic_clinic_i_8b0e0f_idx'),
        ),
        migrations.AddIndex(
            model_name='admission',
            index=models.Index(fields=['discharged'], name='DurielMedic_discharg_f16b68_idx'),
        ),
        migrations.AddIndex(
            model_name='admission',
            index=models.Index(fields=['-date_admitted'], name='DurielMedic_date_ad_6a70d9_idx'),
        ),
    ]

