import uuid

from django.db import migrations, models


SYNC_MODELS = ('MedicalRecord', 'Appointment', 'Vitals', 'Admission', 'FollowUp')


def populate_sync_ids(apps, schema_editor):
    for model_name in SYNC_MODELS:
        model = apps.get_model('DurielMedicApp', model_name)
        for record in model.objects.filter(sync_id__isnull=True).iterator():
            record.sync_id = uuid.uuid4()
            record.save(update_fields=['sync_id'])


class Migration(migrations.Migration):
    dependencies = [
        ('DurielMedicApp', '0002_initial'),
        ('core', '0002_offline_sync_foundation'),
    ]

    operations = [
        *[
            migrations.AddField(
                model_name=model_name.lower(),
                name='sync_id',
                field=models.UUIDField(editable=False, null=True),
            )
            for model_name in SYNC_MODELS
        ],
        migrations.RunPython(populate_sync_ids, migrations.RunPython.noop),
        *[
            migrations.AlterField(
                model_name=model_name.lower(),
                name='sync_id',
                field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
            )
            for model_name in SYNC_MODELS
        ],
    ]
