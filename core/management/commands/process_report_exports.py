from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import ReportExportJob
from core.reporting import (
    export_admission_report,
    export_appointment_report,
    export_consultation_report,
    export_dental_procedure_report,
    export_financial_report,
    export_optical_prescription_report,
    export_patient_report,
    export_prescription_report,
)
from DurielDentalApp.models import DentalAppointment
from DurielEyeApp.models import EyeAppointment
from DurielMedicApp.models import Appointment


APPOINTMENT_MODELS = {
    'general': Appointment,
    'eye': EyeAppointment,
    'dental': DentalAppointment,
}


class Command(BaseCommand):
    help = 'Process queued report CSV exports.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=5)

    def handle(self, *args, **options):
        limit = options['limit']
        processed = 0

        for job_id in list(
            ReportExportJob.objects.filter(status='PENDING')
            .order_by('created_at')
            .values_list('id', flat=True)[:limit]
        ):
            processed += self._process_job(job_id)

        self.stdout.write(self.style.SUCCESS(f'Processed {processed} report export job(s).'))

    def _process_job(self, job_id):
        with transaction.atomic():
            job = (
                ReportExportJob.objects
                .select_for_update()
                .select_related('clinic')
                .get(pk=job_id)
            )
            if job.status != 'PENDING':
                return 0
            job.status = 'RUNNING'
            job.error = ''
            job.save(update_fields=['status', 'error', 'updated_at'])

        try:
            response = self._build_response(job)
            filename = self._filename(job)
            job.file.save(filename, ContentFile(response.content), save=False)
            job.status = 'COMPLETED'
            job.completed_at = timezone.now()
            job.save(update_fields=['file', 'status', 'completed_at', 'updated_at'])
            return 1
        except Exception as exc:
            job.status = 'FAILED'
            job.error = str(exc)
            job.save(update_fields=['status', 'error', 'updated_at'])
            self.stderr.write(self.style.ERROR(f'Failed report export job {job.pk}: {exc}'))
            return 1

    def _build_response(self, job):
        appointment_model = APPOINTMENT_MODELS.get(job.report_scope)
        if job.report_type == 'appointments':
            if not appointment_model:
                raise ValueError(f'Unsupported appointment scope: {job.report_scope}')
            return export_appointment_report(appointment_model, job.start_date, job.end_date, job.clinic_id)
        if job.report_type == 'patients':
            return export_patient_report(job.start_date, job.end_date, job.clinic_id)
        if job.report_type == 'financial':
            return export_financial_report(job.start_date, job.end_date, job.clinic_id)
        if job.report_type == 'prescriptions':
            return export_prescription_report(job.start_date, job.end_date, job.clinic_id)
        if job.report_type == 'consultations':
            return export_consultation_report(job.start_date, job.end_date, job.clinic_id)
        if job.report_type == 'admissions':
            return export_admission_report(job.start_date, job.end_date, job.clinic_id)
        if job.report_type == 'dental_procedures':
            return export_dental_procedure_report(job.start_date, job.end_date, job.clinic_id)
        if job.report_type == 'optical_prescriptions':
            return export_optical_prescription_report(job.start_date, job.end_date, job.clinic_id)
        raise ValueError(f'Unsupported report type: {job.report_type}')

    def _filename(self, job):
        start = job.start_date.date().isoformat()
        end = job.end_date.date().isoformat()
        return f'{job.report_scope}_{job.report_type}_{job.clinic_id}_{start}_to_{end}.csv'
