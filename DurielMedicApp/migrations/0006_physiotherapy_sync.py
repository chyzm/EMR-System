import uuid

from django.db import migrations, models


def populate_sync_ids(apps, schema_editor):
    model = apps.get_model('DurielMedicApp', 'PhysiotherapyRecord')
    for primary_key in model.objects.filter(sync_id__isnull=True).values_list('pk', flat=True).iterator():
        model.objects.filter(pk=primary_key).update(sync_id=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [('DurielMedicApp', '0005_admission_handover')]

    operations = [
        migrations.AddField(
            model_name='physiotherapyrecord',
            name='sync_id',
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(populate_sync_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='physiotherapyrecord',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),
    ]
