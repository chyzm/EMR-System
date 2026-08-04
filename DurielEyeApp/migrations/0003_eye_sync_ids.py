import uuid

from django.db import migrations, models


def populate_eye_sync_ids(apps, schema_editor):
    for model_name in ('EyeAppointment', 'EyeExam', 'EyeFollowUp', 'EyeMedicalRecord'):
        model = apps.get_model('DurielEyeApp', model_name)
        for record in model.objects.filter(sync_id__isnull=True).iterator():
            record.sync_id = uuid.uuid4()
            record.save(update_fields=['sync_id'])


class Migration(migrations.Migration):
    dependencies = [
        ('DurielEyeApp', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='eyeappointment',
            name='sync_id',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='eyeexam',
            name='sync_id',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='eyefollowup',
            name='sync_id',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='eyemedicalrecord',
            name='sync_id',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(populate_eye_sync_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='eyeappointment',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='eyeexam',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='eyefollowup',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='eyemedicalrecord',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
