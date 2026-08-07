param(
    [string]$InstallDir = (Split-Path $PSScriptRoot -Parent),
    [int]$Port = 9000,
    [switch]$StartTasks,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$serverTaskName = "DurielMedic Clinic Server"
$syncTaskName = "DurielMedic Sync Worker"
$updaterTaskName = "DurielMedic Clinic Updater"
$taskNames = @($serverTaskName, $syncTaskName, $updaterTaskName)
$runtimeRoot = Join-Path $env:ProgramData "DurielMedicClinicServer\runtime"
$taskLogDir = Join-Path $runtimeRoot "logs"
$syncPassLock = Join-Path $runtimeRoot "sync-worker.lock"
$syncOwnerLock = Join-Path $runtimeRoot "sync-worker-owner.lock"
New-Item -ItemType Directory -Path $taskLogDir -Force | Out-Null
Start-Transcript -Path (Join-Path $taskLogDir "task-config.log") -Append | Out-Null


function Stop-OrphanedSyncWorkers {
    try {
        $workers = @(
            Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.Name -eq "DurielMedicClinicServer.exe" -and
                    $_.CommandLine -match '--manage\s+sync_worker'
                }
        )

        foreach ($worker in $workers) {
            Write-Host "Stopping stale sync worker PID=$($worker.ProcessId)"
            Stop-Process -Id $worker.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    catch {
        Write-Warning "Unable to enumerate stale sync workers: $_"
    }

    Start-Sleep -Seconds 1

    Remove-Item $syncPassLock -Force -ErrorAction SilentlyContinue
    Remove-Item $syncOwnerLock -Force -ErrorAction SilentlyContinue
}

function Stop-And-UnregisterTask([string]$TaskName) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
}

if ($Uninstall) {
    Stop-And-UnregisterTask $serverTaskName
    Stop-And-UnregisterTask $syncTaskName
    Stop-And-UnregisterTask $updaterTaskName
    Write-Host "DurielMedic background tasks removed. Clinic data in ProgramData was preserved."
    Stop-Transcript | Out-Null
    exit 0
}

$InstallDir = [System.IO.Path]::GetFullPath($InstallDir)
$appExe = Join-Path $InstallDir "DurielMedicClinicServer.exe"
$updaterScript = Join-Path $InstallDir "updater\Update-DurielMedicClinic.ps1"
if (-not (Test-Path $appExe -PathType Leaf)) {
    throw "Desktop executable not found at $appExe"
}
if (-not (Test-Path $updaterScript -PathType Leaf)) {
    throw "Updater script not found at $updaterScript"
}

Stop-ScheduledTask -TaskName $serverTaskName -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName $syncTaskName -ErrorAction SilentlyContinue
Stop-OrphanedSyncWorkers

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$startupTrigger = New-ScheduledTaskTrigger -AtStartup
$syncTrigger = New-ScheduledTaskTrigger -AtStartup
$syncTrigger.Delay = "PT30S"
$updateTrigger = New-ScheduledTaskTrigger -Daily -At 2am

$longRunningSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
    -MultipleInstances IgnoreNew
$updaterSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

$serverAction = New-ScheduledTaskAction `
    -Execute $appExe `
    -Argument "--background-server" `
    -WorkingDirectory $InstallDir
$syncAction = New-ScheduledTaskAction `
    -Execute $appExe `
    -Argument "--manage sync_worker" `
    -WorkingDirectory $InstallDir
$updateAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$updaterScript`" -InstallDir `"$InstallDir`" -Port $Port" `
    -WorkingDirectory $InstallDir

Register-ScheduledTask -TaskName $serverTaskName -Action $serverAction -Trigger $startupTrigger -Principal $principal -Settings $longRunningSettings -Force | Out-Null
Register-ScheduledTask -TaskName $syncTaskName -Action $syncAction -Trigger $syncTrigger -Principal $principal -Settings $longRunningSettings -Force | Out-Null
Register-ScheduledTask -TaskName $updaterTaskName -Action $updateAction -Trigger $updateTrigger -Principal $principal -Settings $updaterSettings -Force | Out-Null

foreach ($taskName in $taskNames) {
    if (-not (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)) {
        throw "Scheduled task registration did not persist: $taskName"
    }
}

if ($StartTasks) {
    Start-ScheduledTask -TaskName $serverTaskName
    Start-Sleep -Seconds 2
    Start-ScheduledTask -TaskName $syncTaskName
}

Write-Host "DurielMedic server, sync, and updater tasks configured for automatic startup."
Stop-Transcript | Out-Null
