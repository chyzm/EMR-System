import uuid

from django.db import migrations, models


def populate_prescription_sync_ids(apps, schema_editor):
    Prescription = apps.get_model('core', 'Prescription')
    for prescription in Prescription.objects.filter(sync_id__isnull=True).iterator():
        prescription.sync_id = uuid.uuid4()
        prescription.save(update_fields=['sync_id'])


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0003_server_sync'),
    ]

    operations = [
        migrations.AddField(
            model_name='prescription',
            name='sync_id',
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(populate_prescription_sync_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='prescription',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
