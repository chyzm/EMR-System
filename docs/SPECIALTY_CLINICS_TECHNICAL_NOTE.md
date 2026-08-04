# Specialty Clinics Technical Note

## Scope

This update standardizes specialty clinic operations for:

- Eye clinics
- Dental clinics

The goal is to make the specialty modules usable for real onboarding while keeping them consistent with DurielMedic’s shared patient, billing, role, navigation, and offline/local-server sync direction.

## Product Design Principles Applied

1. One patient record, specialty-specific clinical charts
   - Patients remain in `core.Patient`.
   - Eye and Dental store specialty records separately.
   - This avoids duplicate patient identities across clinic types.

2. Specialty workflows should match how clinics work
   - Eye: appointment → exam/refraction → consultation record → follow-up → billing.
   - Dental: appointment → dental chart/exam → treatment plan → procedure → follow-up → billing.

3. Billing must see clinical work
   - Billing staff need evidence of what happened clinically.
   - Dental procedures, treatment plans, and exams now appear in the billing activity panel for dental clinics.

4. Sync-ready data
   - Specialty records now have `sync_id` fields.
   - Server sync registration includes Eye and Dental models.
   - This supports central cloud ↔ local clinic database synchronization.

5. Keep navigation predictable
   - Dashboard, appointments, follow-ups, and billing remain shared concepts.
   - Dental now has its own dashboard, appointment list, follow-up list, procedure list, and patient dental chart.

## Eye Clinic Standardization

### Existing Eye Module Reviewed

The Eye module already had:

- Eye dashboard
- Eye appointments
- Eye exams
- Eye medical records
- Eye follow-ups
- Eye reports
- Consultation flow

### Improvements Made

1. Added sync IDs
   - `EyeAppointment.sync_id`
   - `EyeExam.sync_id`
   - `EyeMedicalRecord.sync_id`
   - `EyeFollowUp.sync_id`

2. Added migration
   - `DurielEyeApp/migrations/0003_eye_sync_ids.py`

3. Fixed Eye dashboard patient appointment prefetch
   - Removed incorrect prefetch of regular appointments using the Eye appointment model.
   - Recent patients now correctly use `eye_appointments`.

4. Fixed appointment cancellation route mismatch
   - The URL passed `pk`, but the view expected `appointment_id`.
   - The view now accepts `pk`.
   - Redirect now points to `DurielEyeApp:appointment_list`.

5. Fixed eye exam form cleaning
   - The `clean()` method was accidentally nested inside the form `Meta` class.
   - It is now correctly defined on `EyeExamForm`.
   - Default refraction/pupil fields are applied reliably.

6. Improved Eye exam form borders
   - Eye exam inputs now use visible borders consistent with the rest of the app.

## Dental Clinic Build

The previous Dental module was only a placeholder. It has now been replaced with a functional dental clinic module.

### New Dental Models

1. `DentalAppointment`
   - Handles appointment scheduling and chair workflow.
   - Fields include patient, provider, clinic, visit type, payment type, date/time, chief complaint, notes, and status.

2. `DentalExam`
   - Captures dental assessment.
   - Fields include chief complaint, medical alerts, extraoral exam, intraoral exam, periodontal findings, occlusion, diagnosis, treatment recommendation, and tooth chart JSON.

3. `DentalTreatmentPlan`
   - Captures proposed treatment plans.
   - Fields include diagnosis, proposed treatment, priority, estimated cost, consent, and status.

4. `DentalProcedure`
   - Captures what was actually done.
   - Fields include tooth numbers, procedure name, materials, anesthesia, notes, cost, status, provider, and date/time.

5. `DentalFollowUp`
   - Handles post-treatment review scheduling and completion.

6. `DentalMedicalRecord`
   - Stores additional dental clinical notes, imaging notes, consent records, prescriptions, and other records.

### New Dental Forms

Added `DurielDentalApp/forms.py` with:

- `DentalAppointmentForm`
- `DentalExamForm`
- `DentalTreatmentPlanForm`
- `DentalProcedureForm`
- `DentalFollowUpForm`
- `DentalMedicalRecordForm`

Forms use visible input borders and clinic-aware querysets.

### New Dental Views

Added production workflow views:

- Dental dashboard
- Appointment list
- Appointment creation
- Appointment editing
- Appointment detail
- Appointment status update
- Patient dental chart
- Record dental exam
- Create treatment plan
- Record procedure
- Schedule follow-up
- Complete follow-up
- Add dental record
- Procedure list/search
- Dentist appointment count API

### New Dental Routes

Added routes in `DurielDentalApp/urls.py`:

- `/dental/dashboard/`
- `/dental/appointments/`
- `/dental/appointments/create/`
- `/dental/appointments/<id>/`
- `/dental/appointments/<id>/edit/`
- `/dental/appointments/<id>/status/<status>/`
- `/dental/patients/<patient_id>/chart/`
- `/dental/patients/<patient_id>/exam/`
- `/dental/patients/<patient_id>/treatment-plan/`
- `/dental/patients/<patient_id>/procedure/`
- `/dental/patients/<patient_id>/follow-up/`
- `/dental/patients/<patient_id>/records/add/`
- `/dental/follow-up/`
- `/dental/procedures/`

### New Dental Templates

Added:

- `templates/dental/dashboard.html`
- `templates/dental/appointments/appointment_list.html`
- `templates/dental/appointments/appointment_form.html`
- `templates/dental/appointments/appointment_detail.html`
- `templates/dental/forms/form_page.html`
- `templates/dental/patient_chart.html`
- `templates/dental/followups/list.html`
- `templates/dental/procedures/list.html`

## Navigation Updates

The base navigation now supports Dental clinic routing:

- Dental dashboard
- Dental appointments
- Dental procedures
- Dental follow-ups

The shared patient detail page now shows an `Open Dental Chart` action when the active clinic type is `DENTAL`.

## Billing Updates

The billing form now includes Dental activity when the selected clinic is dental:

- Dental procedures
- Dental treatment plans
- Dental exams

This helps reception create accurate bills based on clinical work performed.

## Sync Updates

The following models are now registered as server-syncable:

- `DurielEyeApp.EyeAppointment`
- `DurielEyeApp.EyeExam`
- `DurielEyeApp.EyeMedicalRecord`
- `DurielEyeApp.EyeFollowUp`
- `DurielDentalApp.DentalAppointment`
- `DurielDentalApp.DentalExam`
- `DurielDentalApp.DentalTreatmentPlan`
- `DurielDentalApp.DentalProcedure`
- `DurielDentalApp.DentalFollowUp`
- `DurielDentalApp.DentalMedicalRecord`

## Admin Updates

Dental models are registered in Django admin for support, debugging, and onboarding inspection.

## Migration Files Added

- `DurielEyeApp/migrations/0003_eye_sync_ids.py`
- `DurielDentalApp/migrations/0003_standard_dental_clinic.py`

## Deployment Notes

Before onboarding clinics, run:

```bash
python3 manage.py migrate
python3 manage.py collectstatic --noinput
```

Then restart the server.

## Verification Performed

Python compile checks passed for:

- Eye models/forms/views/urls/migrations
- Dental models/forms/views/urls/admin/migrations
- Shared billing view
- Server sync registration

Full Django runtime tests were not executed in this shell because Django is not installed in the current environment.

## Recommended Onboarding Test Flow

### Eye Clinic

1. Create/select an Eye clinic.
2. Register a patient.
3. Create an eye appointment.
4. Record eye exam/refraction.
5. Begin and complete consultation.
6. Add eye medical record.
7. Schedule follow-up.
8. Create bill and confirm Eye activity is visible.

### Dental Clinic

1. Create/select a Dental clinic.
2. Register a patient.
3. Create a dental appointment.
4. Open the patient dental chart.
5. Record dental exam.
6. Create treatment plan.
7. Record procedure.
8. Schedule follow-up.
9. Open billing and confirm Dental procedure/plan/exam appears.
10. Confirm dashboard, appointment list, procedure list, and follow-up list work.

## Remaining Recommendations

Before large-scale onboarding:

1. Run full Django checks/tests in the real virtual environment.
2. Add dental-specific service price templates, e.g. extraction, scaling, filling, root canal.
3. Consider a visual odontogram UI later. The current implementation supports structured JSON, but a click-based tooth chart would be better for high-volume dental clinics.
4. Add dental consent document generation for surgical/extraction/root canal procedures.
5. Pilot with one Eye clinic and one Dental clinic before broad rollout.
