param(
    [Parameter(Mandatory = $true)]
    [string]$ActivationUrl,

    [string]$InstallDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).ProviderPath,
    [int]$Port = 9000
)

$ErrorActionPreference = "Stop"

Set-Location $InstallDir

$logsDir = Join-Path $InstallDir "logs"
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}
$installLog = Join-Path $logsDir "install-local-server.log"
Start-Transcript -Path $installLog -Append | Out-Null
trap {
    Write-Host "DurielMedic local server installation failed. See log: $installLog"
    Stop-Transcript | Out-Null
    throw
}

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
    $secretBytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($secretBytes)
    $rng.Dispose()
    $secret = [Convert]::ToBase64String($secretBytes)
    @"
SECRET_KEY=$secret
DEBUG=True
ALLOWED_HOSTS=*
LOCAL_SERVER_PORT=$Port
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

$launcherScript = Join-Path $InstallDir "Open-DurielMedicClinic.ps1"
@"
param(
    [int]`$Port = $Port
)

`$ErrorActionPreference = "SilentlyContinue"
Start-ScheduledTask -TaskName "DurielMedic Clinic Server"
Start-Sleep -Seconds 2
Start-Process "http://localhost:`$Port"
"@ | Set-Content -Path $launcherScript -Encoding UTF8

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

New-NetFirewallRule `
    -DisplayName "DurielMedic Clinic Server $Port" `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort $Port `
    -Action Allow `
    -Profile Private,Domain `
    -ErrorAction SilentlyContinue | Out-Null

Start-ScheduledTask -TaskName "DurielMedic Clinic Server"
Start-ScheduledTask -TaskName "DurielMedic Sync Worker"

Write-Host "DurielMedic Clinic Server installed."
Write-Host "Open this on clinic devices: http://<clinic-server-ip>:$Port"
Stop-Transcript | Out-Null
