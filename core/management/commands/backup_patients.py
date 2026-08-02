from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils.text import slugify
from django.apps import apps
import csv
import io
import zipfile
import datetime
import io as _io

from core.models import Clinic, Patient


class Command(BaseCommand):
    help = 'Backup patients CSV and uploaded files for a clinic (use --clinic <id> or --all)'

    def add_arguments(self, parser):
        parser.add_argument('--clinic', type=int, help='Clinic ID to backup')
        parser.add_argument('--all', action='store_true', help='Backup all clinics')

    def handle(self, *args, **options):
        clinic_id = options.get('clinic')
        all_flag = options.get('all')

        if not clinic_id and not all_flag:
            self.stdout.write(self.style.ERROR('You must provide --clinic <id> or --all'))
            return

        if all_flag:
            clinics = Clinic.objects.all()
        else:
            clinics = Clinic.objects.filter(id=clinic_id)

        for clinic in clinics:
            self.stdout.write(f"Backing up clinic {clinic.id} - {clinic.name}")
            patients = Patient.objects.filter(clinic=clinic).order_by('last_name', 'first_name')
            date_str = datetime.date.today().strftime('%Y%m%d')

            # --- CSV ---
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(['patient_id', 'first_name', 'last_name', 'date_of_birth', 'gender', 'contact', 'email', 'address', 'emergency_contact', 'created_at'])
            for p in patients:
                writer.writerow([
                    p.patient_id,
                    p.first_name,
                    p.last_name,
                    p.date_of_birth,
                    p.gender,
                    p.contact,
                    p.email or '',
                    p.address or '',
                    p.emergency_contact or '',
                    p.created_at,
                ])

            csv_name = f'backups/clinic_{clinic.id}/patients_export_{date_str}.csv'
            default_storage.save(csv_name, ContentFile(csv_buffer.getvalue().encode('utf-8')))
            self.stdout.write(self.style.SUCCESS(f'Saved CSV to {csv_name}'))

            # --- ZIP of uploaded files ---
            zip_buffer = _io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for p in patients:
                    folder_name = f"{slugify(p.full_name)}_{p.patient_id}"

                    # include patient profile picture
                    try:
                        if getattr(p, 'profile_picture'):
                            pf = p.profile_picture
                            if pf and getattr(pf, 'name', None) and default_storage.exists(pf.name):
                                with default_storage.open(pf.name, 'rb') as fh:
                                    arcname = f"{folder_name}/{pf.name.split('/')[-1]}"
                                    zf.writestr(arcname, fh.read())
                    except Exception:
                        pass

                    # scan installed models for FileField/ImageField with FK 'patient'
                    for model in apps.get_models():
                        try:
                            # only consider models that have a FK named 'patient'
                            if any(f.name == 'patient' for f in model._meta.fields):
                                file_fields = [f for f in model._meta.fields if f.get_internal_type() in ('FileField', 'ImageField')]
                                if not file_fields:
                                    continue
                                instances = model.objects.filter(patient=p)
                                for inst in instances:
                                    for ff in file_fields:
                                        val = getattr(inst, ff.name)
                                        if val and getattr(val, 'name', None) and default_storage.exists(val.name):
                                            try:
                                                with default_storage.open(val.name, 'rb') as fh:
                                                    arcname = f"{folder_name}/{val.name.split('/')[-1]}"
                                                    zf.writestr(arcname, fh.read())
                                            except Exception:
                                                continue
                        except Exception:
                            continue

            zip_buffer.seek(0)
            zip_name = f'backups/clinic_{clinic.id}/patient_files_backup_{date_str}.zip'
            default_storage.save(zip_name, ContentFile(zip_buffer.getvalue()))
            self.stdout.write(self.style.SUCCESS(f'Saved ZIP to {zip_name}'))

        self.stdout.write(self.style.SUCCESS('Backup(s) completed'))
