param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").ProviderPath
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path $ProjectRoot).ProviderPath
Set-Location $ProjectRoot

$commonArgs = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--add-data", "DurielMedic;DurielMedic",
    "--add-data", "DurielMedicApp;DurielMedicApp",
    "--add-data", "DurielEyeApp;DurielEyeApp",
    "--add-data", "DurielDentalApp;DurielDentalApp",
    "--add-data", "core;core",
    "--add-data", "templates;templates",
    "--add-data", "static;static",
    "--add-data", "staticfiles;staticfiles",
    "--add-data", "manage.py;.",
    "--add-data", "requirements.txt;.",
    "--collect-data", "tzdata",
    "--collect-data", "crispy_forms",
    "--collect-data", "crispy_tailwind",
    "--hidden-import", "django.core.management.commands.migrate",
    "--hidden-import", "django.core.management.commands.collectstatic",
    "--hidden-import", "core.management.commands.activate_local_clinic",
    "--hidden-import", "core.management.commands.sync_worker",
    "--hidden-import", "waitress",
    "desktop_launcher.py"
)

$pyInstallerExeCandidates = @(
    (Join-Path $ProjectRoot "env\Scripts\pyinstaller.exe"),
    (Join-Path $ProjectRoot ".venv\Scripts\pyinstaller.exe")
)

$pyInstallerExe = $pyInstallerExeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($pyInstallerExe) {
    & $pyInstallerExe "--name" "DurielMedicClinicServer" @commonArgs
    exit $LASTEXITCODE
}

$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    & py -3 -m PyInstaller "--name" "DurielMedicClinicServer" @commonArgs
    exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & python -m PyInstaller "--name" "DurielMedicClinicServer" @commonArgs
    exit $LASTEXITCODE
}

$pyInstallerCommand = Get-Command pyinstaller -ErrorAction SilentlyContinue
if ($pyInstallerCommand) {
    & $pyInstallerCommand.Source "--name" "DurielMedicClinicServer" @commonArgs
    exit $LASTEXITCODE
}

throw "PyInstaller was not found. Install it with: py -3 -m pip install pyinstaller"
