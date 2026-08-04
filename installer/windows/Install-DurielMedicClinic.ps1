param(
    [Parameter(Mandatory = $true)]
    [string]$ActivationUrl,

    [string]$InstallDir = $PSScriptRoot,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

Set-Location $InstallDir

$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) {
    $pythonCmd = "py"
    $pythonArgs = @("-3")
} else {
    $pythonExe = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonExe) {
        throw "Python 3 was not found. Install Python 3 and run this installer again."
    }
    $pythonCmd = "python"
    $pythonArgs = @()
}

if (-not (Test-Path ".env")) {
    $secret = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
    @"
SECRET_KEY=$secret
DEBUG=True
ALLOWED_HOSTS=*
"@ | Set-Content -Path ".env" -Encoding UTF8
}

if (-not (Test-Path ".venv")) {
    & $pythonCmd @pythonArgs -m venv .venv
}

$venvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt
& $venvPython manage.py migrate
& $venvPython manage.py activate_local_clinic $ActivationUrl

$webAction = New-ScheduledTaskAction `
    -Execute $venvPython `
    -Argument "-m waitress --listen=0.0.0.0:$Port DurielMedic.wsgi:application" `
    -WorkingDirectory $InstallDir
$syncAction = New-ScheduledTaskAction `
    -Execute $venvPython `
    -Argument "manage.py sync_worker" `
    -WorkingDirectory $InstallDir
$updateScript = Join-Path $InstallDir "installer\windows\Update-DurielMedicClinic.ps1"
$updateAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$updateScript`" -InstallDir `"$InstallDir`"" `
    -WorkingDirectory $InstallDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$updateTrigger = New-ScheduledTaskTrigger -Daily -At 2am
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

Register-ScheduledTask -TaskName "DurielMedic Clinic Server" -Action $webAction -Trigger $trigger -Principal $principal -Force | Out-Null
Register-ScheduledTask -TaskName "DurielMedic Sync Worker" -Action $syncAction -Trigger $trigger -Principal $principal -Force | Out-Null
Register-ScheduledTask -TaskName "DurielMedic Clinic Updater" -Action $updateAction -Trigger $updateTrigger -Principal $principal -Force | Out-Null

Start-ScheduledTask -TaskName "DurielMedic Clinic Server"
Start-ScheduledTask -TaskName "DurielMedic Sync Worker"

Write-Host "DurielMedic Clinic Server installed."
Write-Host "Open this on clinic devices: http://<clinic-server-ip>:$Port"
