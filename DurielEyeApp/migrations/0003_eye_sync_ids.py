import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('DurielEyeApp', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='eyeappointment',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name='eyeexam',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name='eyefollowup',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name='eyemedicalrecord',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
