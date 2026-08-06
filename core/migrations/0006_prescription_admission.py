import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0005_expand_server_sync'),
        ('DurielMedicApp', '0006_physiotherapy_sync'),
    ]

    operations = [
        migrations.AddField(
            model_name='prescription',
            name='admission',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='prescriptions',
                to='DurielMedicApp.admission',
            ),
        ),
        migrations.AlterField(
            model_name='prescription',
            name='prescribed_by',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='prescriptions',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
