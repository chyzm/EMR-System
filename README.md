# DurielMedic EMR

DurielMedic now supports two offline layers that are intentionally separate:

- Browser offline mode uses the existing IndexedDB queue and service worker. This lets one browser keep working when the browser temporarily loses connection.
- Clinic local server mode runs the Django app inside the clinic, usually with SQLite. The clinic server keeps its own database, records local changes in a durable server outbox, and syncs with the central server in the background when internet is available.

This means the current IndexedDB setup is not replaced. It still works as a device/browser safety net. The local server adds clinic-wide offline capability.

## Sync Design

The server sync follows an outbox plus pull-cursor design.

When a supported clinical model changes, Django signals record the change in `ServerSyncChange`. When the server role is `local`, the same change is also queued in `ServerSyncOutbox`.

The local worker does two jobs:

1. Push local `ServerSyncOutbox` items to the central server.
2. Pull central `ServerSyncChange` items that happened after the local cursor.

That second step is what covers the important case where an action was done away from the clinic local database connection. For example, if someone updates the central/cloud server while the clinic local server is offline, the clinic server pulls and applies that change when internet returns.

The current implementation supports these syncable records:

- `core.Patient`
- `DurielMedicApp.Appointment`
- `DurielMedicApp.Vitals`
- `DurielMedicApp.MedicalRecord`
- `DurielMedicApp.Admission`
- `DurielMedicApp.AdmissionHandover`
- `DurielMedicApp.MedicationAdministration`
- `DurielMedicApp.FollowUp`
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
- `core.Billing`
- `core.Payment`
- `core.Prescription`

Each synced record uses its `sync_id` as the stable identity across servers. Sync operations are idempotent through `operation_id`, so retrying the same event should not create duplicate central changes.

## Clinic Modules

DurielMedic supports three clinic operating modes from the same shared platform:

- General clinic / hospital
- Eye clinic
- Dental clinic

Patients, billing, users, settings, notifications, and offline/local-server sync remain shared. Specialty apps add the clinical workflows that are specific to each clinic type.

## General Clinic / Hospital Workflow

The General clinic module supports:

- Patient registration
- Appointments
- Vitals
- Consultation notes
- Prescriptions
- Admissions
- Doctor/Nurse admission handovers
- Medication administration chart
- Discharge documentation
- Follow-ups
- Lab queue
- Billing and payment

Admission records include:

- Patient
- Ward
- Bed
- Admission type
- Admission source
- Attending doctor
- Provisional diagnosis
- Reason for admission
- Admitted by
- Admission date/time
- Expected discharge date
- Admission status

Discharge records include:

- Discharge diagnosis
- Discharge condition
- Discharge summary
- Discharge instructions
- Follow-up plan
- Discharged by
- Discharge date/time

Admission handovers allow doctors and nurses to record shift/clinical transfer notes with:

- Handover type
- Receiving staff
- Summary
- Current condition
- Pending tasks
- Concerns

## Eye Clinic Workflow

The Eye clinic module supports a standard eye-clinic flow:

1. Register/select patient.
2. Schedule Eye appointment.
3. Begin consultation.
4. Record Eye exam/refraction.
5. Add Eye medical record.
6. Create prescriptions where needed.
7. Schedule follow-up.
8. Bill the patient.

Eye clinical records include:

- Visual acuity right/left
- Intraocular pressure right/left
- Slit lamp findings
- Fundus exam findings
- Refraction right/left
- Sphere/cylinder/axis/add values
- Pupil size
- Notes

The Eye module is sync-ready through `sync_id` fields on Eye appointments, exams, medical records, and follow-ups.

## Dental Clinic Workflow

The Dental module is now a full clinic workflow, not a placeholder.

Supported Dental functions:

- Dental dashboard
- Dental appointments
- Chair workflow statuses
- Patient dental chart
- Dental exams
- Tooth chart JSON support
- Treatment plans
- Consent tracking
- Dental procedures
- Procedure cost capture
- Dental follow-ups
- Dental medical records
- Procedure search/list
- Billing activity visibility

Recommended Dental flow:

1. Register/select patient.
2. Schedule Dental appointment.
3. Open the patient Dental Chart.
4. Record Dental exam.
5. Create treatment plan.
6. Record procedure when treatment is done.
7. Schedule follow-up.
8. Open Billing and bill from visible Dental activity.

Dental procedures and treatment plans include cost fields so front desk/billing can see what was done and charge correctly.

The current tooth chart is JSON-backed. Example:

```json
{
  "11": "caries",
  "36": "missing",
  "44": "restored"
}
```

A visual click-based odontogram can be added later, but the current structure is already suitable for storing standardized tooth findings.

## Billing Visibility

Billing can see recent patient activity before creating a bill.

General clinic billing context includes:

- Appointments
- Admissions
- Prescriptions
- Clinical records

Dental billing context additionally includes:

- Dental procedures
- Dental treatment plans
- Dental exams

The billing form also allows manual service/cost entry for items that are not yet in the service price list.

## Add-On Activation Model

Clinic local server support is an optional add-on. Cloud access still works normally, and browser IndexedDB offline mode still works normally.

For clinics that want a local server, the preferred setup is:

1. The clinic admin copies an activation URL from the cloud account settings.
2. Give the clinic the Windows installer, not the source repo.
3. The installer asks for the activation URL.
4. The local server activates itself, imports clinic metadata and non-superuser clinic users, runs migrations, and starts the local web service plus background sync worker on boot.
5. Future code/template updates are delivered through the updater manifest, so the clinic does not need a new installer for every release.

The clinic no longer needs to manually enter:

- `SYNC_SERVER_ROLE`
- `SYNC_CENTRAL_URL`
- `SYNC_CLINIC_SYNC_ID`
- `SYNC_NODE_ID`
- `SYNC_SHARED_SECRET`

Those values are fetched from the activation URL and stored in local SQLite in `ServerSyncState`.

## Environment Variables

Common variables:

```env
SECRET_KEY=change-me
DEBUG=True
SYNC_BATCH_SIZE=25
SYNC_INTERVAL_SECONDS=30
SYNC_REQUEST_TIMEOUT_SECONDS=20
```

Central server:

```env
SYNC_SERVER_ROLE=central
SYNC_SHARED_SECRET=use-a-long-random-runtime-sync-secret
SYNC_ACTIVATION_TOKEN=use-a-different-long-random-activation-token
SYNC_UPDATE_MANIFEST_URL=https://durielmedic.com.ng/releases/update-manifest.json
```

Clinic local server package:

```env
SECRET_KEY=replace-with-a-secure-local-secret
DEBUG=True
```

The activation command fills the local sync settings in SQLite.

## Windows Clinic Server Installer

Use Inno Setup to build a Windows `.exe` installer. The client should receive only the generated setup file, not the Git repository.

Build the installer on your own/release machine:

```powershell
.\installer\windows\Build-InnoPackage.ps1 `
  -Version "1.0.0" `
  -PackageBaseUrl "https://durielmedic.com.ng/releases"
```

This stages a clean package in:

```text
dist\durielmedic-clinic-server
```

Then Inno Setup creates:

```text
dist\DurielMedic-Clinic-Server-Setup.exe
```

The build also creates update artifacts:

```text
dist\durielmedic-clinic-server-1.0.0.zip
dist\update-manifest.json
```

Upload both files to the release location configured by:

```env
SYNC_UPDATE_MANIFEST_URL=https://durielmedic.com.ng/releases/update-manifest.json
```

The clinic admin gets the activation link from `https://durielmedic.com.ng`:

1. Sign in.
2. Select the clinic.
3. Open `Settings`.
4. Copy the link from `Local Server Activation`.

On the clinic server PC:

1. Run `DurielMedic-Clinic-Server-Setup.exe`.
2. Paste the activation URL when prompted.
3. Finish setup.

The installer creates startup tasks for:

- `DurielMedic Clinic Server`
- `DurielMedic Sync Worker`
- `DurielMedic Clinic Updater`

Clinic devices then open:

```text
http://<local-server-ip>:9000
```

Do not install the repo on the clinic machine. The clinic only receives the `.exe` installer.

The Windows installer installs the local app into:

```text
C:\ProgramData\DurielMedic Clinic Server
```

This avoids the write-permission problems that happen when the app database, `.env`, logs, and updater files are placed under `C:\Program Files`.

The desktop shortcut opens:

```text
http://localhost:9000
```

## Local Updates

The clinic server updater checks the activation-provided `update_manifest_url` daily at 2:00 AM.

The manifest points to a versioned release zip and includes its SHA-256 hash. When a newer version is available, the updater:

- downloads the release zip
- verifies the hash
- stops the local web and sync scheduled tasks
- copies the current app files into `rollback\before-<version>-<timestamp>`
- replaces app code/templates/static files
- preserves `.env`, `.venv`, `db.sqlite3`, `media`, and `logs`
- runs `pip install -r requirements.txt`
- runs `python manage.py migrate`
- restarts the local web and sync tasks
- restores the rollback copy if the update or migration fails

This is how code/template updates reach the local clinic server without rebuilding or rerunning the Inno installer every time.

To update installed clinics after a new release:

1. Deploy the same code to PythonAnywhere.
2. Build the local update package with a new version:

```powershell
.\installer\windows\Build-InnoPackage.ps1 `
  -Version "1.0.1" `
  -PackageBaseUrl "https://durielmedic.com.ng/releases"
```

3. Upload these two files to your `/releases/` static folder:

```text
dist\durielmedic-clinic-server-1.0.1.zip
dist\update-manifest.json
```

4. The clinic updater applies the update automatically at 2:00 AM, or you can run the `DurielMedic Clinic Updater` scheduled task manually.

## What Activation Imports

The activation URL returns the payload needed by the local package:

- central server URL
- runtime sync token
- clinic `sync_id`
- clinic name/type/contact metadata
- allowed clinic users

Superusers are intentionally not included in the local activation payload. Only active, non-superuser users assigned to that clinic are imported locally.

## Client Instructions

Send clinics:

- `DurielMedic-Clinic-Server-Setup.exe`
- [CLINIC_INSTALLATION.md](CLINIC_INSTALLATION.md)

The clinic does not need repository access, Git, Docker, or command-line setup.

SQLite is already the default DB:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
```

## Central Server Setup

On the central/cloud server, configure:

```env
SYNC_SERVER_ROLE=central
SYNC_SHARED_SECRET=replace-with-a-long-random-secret
SYNC_ACTIVATION_TOKEN=replace-with-a-different-long-random-secret
SYNC_UPDATE_MANIFEST_URL=https://durielmedic.com.ng/releases/update-manifest.json
```

Then run:

```bash
python3 manage.py migrate
python3 manage.py collectstatic --noinput
```

The central server exposes:

- `GET /api/server-sync/health/`
- `POST /api/server-sync/push/`
- `GET /api/server-sync/pull/`

All server sync requests must include:

```text
X-Sync-Token: <SYNC_SHARED_SECRET>
```

Activation requests use either the `token` query string parameter from the activation URL or:

```text
X-Sync-Activation-Token: <SYNC_ACTIVATION_TOKEN>
```

## Running the Worker in Production

On Windows, the Inno installer registers the web server, sync worker, and updater as Scheduled Tasks. They restart automatically on machine boot.

For real clinic deployments, do not use Django `runserver` as the long-running local web server. `runserver` is acceptable for pilot/internal testing, but the clinic installer should run the app through a production WSGI runner such as Waitress:

```powershell
waitress-serve --listen=0.0.0.0:9000 DurielMedic.wsgi:application
```

The sync worker remains a separate background process:

```bash
python3 manage.py sync_worker
```

The installer should register both the WSGI web process and the sync worker to start automatically on boot.

## Onboarding Checklist

Before onboarding a clinic:

1. Deploy latest code to the cloud server.
2. Run migrations.
3. Run `collectstatic`.
4. Restart the cloud web app.
5. Log in as admin.
6. Create/select the clinic.
7. Confirm clinic type is correct:
   - `GENERAL`
   - `EYE`
   - `DENTAL`
8. Add clinic users.
9. Configure service price list.
10. For local-server clinics, generate the activation link from Settings.
11. Send the clinic only the installer, not the source repository.

Recommended pilot tests:

- Register a patient.
- Create appointment.
- Complete the relevant clinic workflow.
- Create bill.
- Record payment.
- Confirm records appear after page refresh.
- If using local server, confirm cloud ↔ local sync after internet restoration.

For General clinic/hospital:

- Record vitals.
- Begin consultation.
- Admit patient.
- Record doctor/nurse handover.
- Record medication administration.
- Discharge patient.
- Confirm billing sees clinical activity.

For Eye clinic:

- Create Eye appointment.
- Record Eye exam/refraction.
- Add Eye medical record.
- Schedule Eye follow-up.
- Confirm billing works.

For Dental clinic:

- Create Dental appointment.
- Open Dental Chart.
- Record Dental exam.
- Create treatment plan.
- Record procedure.
- Schedule Dental follow-up.
- Confirm Dental procedures/plans/exams appear in Billing.

## Important Operational Notes

- Keep `SYNC_SHARED_SECRET` private and long. Rotate it if exposed.
- Keep `SYNC_ACTIVATION_TOKEN` private. Treat activation URLs as sensitive because they can provision a local clinic server.
- Back up each clinic SQLite database regularly.
- The browser IndexedDB queue still needs the app opened online once before offline browser mode can work.
- The server worker only runs while the local server machine is powered on.
- Failed server outbox items stay visible in `ServerSyncOutbox` with `last_error` for troubleshooting.
- Clinical records should be treated as append-first where possible. Silent overwrites are risky in EMR systems.

## Files Added

- `core/server_sync.py`: serialization, capture helpers, push/pull logic, and remote apply logic.
- `core/management/commands/sync_worker.py`: background worker.
- `core/management/commands/activate_local_clinic.py`: local activation from cloud URL.
- `installer/windows/DurielMedicClinicServer.iss`: Inno Setup installer definition.
- `installer/windows/Build-InnoPackage.ps1`: Windows release-package builder.
- `installer/windows/Install-DurielMedicClinic.ps1`: installed-machine activation and startup task setup.
- `installer/windows/Update-DurielMedicClinic.ps1`: installed-machine code/template updater.
- `core/migrations/0003_server_sync.py`: durable sync tables.
- `CLINIC_INSTALLATION.md`: clinic-facing installation instructions.
- `DurielMedicApp/migrations/0004_admission_inpatient_chart.py`: admission/discharge/medication chart expansion.
- `DurielMedicApp/migrations/0005_admission_handover.py`: doctor/nurse handover records.
- `DurielEyeApp/migrations/0003_eye_sync_ids.py`: Eye sync identities.
- `DurielDentalApp/forms.py`: Dental workflow forms.
- `DurielDentalApp/migrations/0003_standard_dental_clinic.py`: standard Dental clinic data model.
- `templates/dental/`: Dental dashboard, appointments, chart, follow-up, procedure, and form templates.
- `docs/SPECIALTY_CLINICS_TECHNICAL_NOTE.md`: detailed product/technical note for Eye and Dental standardization.

## Additional Technical Notes

See:

- [Specialty Clinics Technical Note](docs/SPECIALTY_CLINICS_TECHNICAL_NOTE.md)
