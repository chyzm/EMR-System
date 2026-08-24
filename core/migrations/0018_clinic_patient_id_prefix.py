from django.db import migrations, models


def clinic_patient_id_base(name):
    compact_name = ''.join(str(name or '').upper().split())
    alnum_name = ''.join(char for char in compact_name if char.isalnum())
    return (alnum_name[:3] or 'CLI')


def assign_patient_id_prefixes(apps, schema_editor):
    Clinic = apps.get_model('core', 'Clinic')
    used = set()
    for clinic in Clinic.objects.order_by('created_at', 'id'):
        base = clinic_patient_id_base(clinic.name)
        prefix = base
        suffix = 1
        while prefix in used:
            prefix = f'{base}{suffix}'
            suffix += 1
        clinic.patient_id_prefix = prefix
        clinic.save(update_fields=['patient_id_prefix'])
        used.add(prefix)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_paymenttransaction_pendingclinicregistration_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='clinic',
            name='patient_id_prefix',
            field=models.CharField(blank=True, editable=False, max_length=8, null=True, unique=True),
        ),
        migrations.RunPython(assign_patient_id_prefixes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='clinic',
            name='patient_id_prefix',
            field=models.CharField(editable=False, max_length=8, unique=True),
        ),
        migrations.AlterField(
            model_name='patient',
            name='patient_id',
            field=models.CharField(editable=False, max_length=20, primary_key=True, serialize=False, unique=True),
        ),
    ]
