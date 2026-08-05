import uuid

from django.db import migrations, models


MODELS = (
    'servicepricelist',
    'medicationcategory',
    'clinicmedication',
    'stockmovement',
    'notification',
    'notificationread',
    'labtestcategory',
    'labtest',
    'labtestorder',
    'labtestresult',
)


def populate_sync_ids(apps, schema_editor):
    for model_name in MODELS:
        model = apps.get_model('core', model_name)
        for primary_key in model.objects.filter(sync_id__isnull=True).values_list('pk', flat=True).iterator():
            model.objects.filter(pk=primary_key).update(sync_id=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [('core', '0004_prescription_sync_id')]

    operations = [
        *[
            migrations.AddField(
                model_name=model_name,
                name='sync_id',
                field=models.UUIDField(null=True, editable=False),
            )
            for model_name in MODELS
        ],
        migrations.RunPython(populate_sync_ids, migrations.RunPython.noop),
        *[
            migrations.AlterField(
                model_name=model_name,
                name='sync_id',
                field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
            )
            for model_name in MODELS
        ],
    ]
