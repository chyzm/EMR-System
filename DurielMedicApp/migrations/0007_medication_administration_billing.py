import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('DurielMedicApp', '0006_physiotherapy_sync'),
        ('core', '0006_prescription_admission'),
    ]

    operations = [
        migrations.AddField(
            model_name='medicationadministration',
            name='billing',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='medication_administrations',
                to='core.billing',
            ),
        ),
        migrations.AddField(
            model_name='medicationadministration',
            name='quantity_administered',
            field=models.PositiveIntegerField(default=1),
        ),
    ]
