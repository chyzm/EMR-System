import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


SYNC_MODELS = ('Clinic', 'Patient', 'Billing', 'Payment')


def populate_sync_ids(apps, schema_editor):
    for model_name in SYNC_MODELS:
        model = apps.get_model('core', model_name)
        for record in model.objects.filter(sync_id__isnull=True).iterator():
            record.sync_id = uuid.uuid4()
            record.save(update_fields=['sync_id'])


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='clinic',
            name='sync_id',
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name='patient',
            name='sync_id',
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name='billing',
            name='sync_id',
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='sync_id',
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(populate_sync_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='clinic',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='patient',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='billing',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='payment',
            name='sync_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.CreateModel(
            name='SyncOperation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operation_id', models.UUIDField(editable=False, unique=True)),
                ('device_id', models.CharField(max_length=64)),
                ('action', models.CharField(max_length=50)),
                ('status', models.CharField(choices=[('PROCESSING', 'Processing'), ('SYNCED', 'Synced'), ('FAILED', 'Failed')], default='PROCESSING', max_length=12)),
                ('result', models.JSONField(blank=True, default=dict)),
                ('error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('clinic', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sync_operations', to='core.clinic')),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['created_at'],
                'indexes': [
                    models.Index(fields=['clinic', 'status', 'created_at'], name='core_syncop_clinic_status_idx'),
                    models.Index(fields=['device_id', 'created_at'], name='core_syncop_device_created_idx'),
                ],
            },
        ),
    ]
