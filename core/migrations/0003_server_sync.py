import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0002_offline_sync_foundation'),
    ]

    operations = [
        migrations.CreateModel(
            name='ServerSyncChange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operation_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('model_label', models.CharField(max_length=120)),
                ('action', models.CharField(max_length=20)),
                ('record_sync_id', models.UUIDField(blank=True, null=True)),
                ('origin_node_id', models.CharField(blank=True, max_length=100)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('clinic', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='server_sync_changes', to='core.clinic')),
            ],
            options={
                'ordering': ['id'],
                'indexes': [
                    models.Index(fields=['clinic', 'id'], name='core_srvchg_clinic_id_idx'),
                    models.Index(fields=['origin_node_id', 'id'], name='core_srvchg_origin_id_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='ServerSyncOutbox',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operation_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('model_label', models.CharField(max_length=120)),
                ('action', models.CharField(max_length=20)),
                ('record_sync_id', models.UUIDField(blank=True, null=True)),
                ('origin_node_id', models.CharField(blank=True, max_length=100)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('SYNCING', 'Syncing'), ('SYNCED', 'Synced'), ('FAILED', 'Failed')], default='PENDING', max_length=12)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('last_error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('synced_at', models.DateTimeField(blank=True, null=True)),
                ('clinic', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='server_sync_outbox', to='core.clinic')),
            ],
            options={
                'ordering': ['created_at'],
                'indexes': [
                    models.Index(fields=['clinic', 'status', 'created_at'], name='core_srvout_clinic_status_idx'),
                    models.Index(fields=['model_label', 'record_sync_id'], name='core_srvout_model_record_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='ServerSyncState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=100, unique=True)),
                ('value', models.JSONField(blank=True, default=dict)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['key'],
            },
        ),
    ]
