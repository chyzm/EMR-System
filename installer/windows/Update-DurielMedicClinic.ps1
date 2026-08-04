param(
    [string]$InstallDir = $PSScriptRoot
)

$ErrorActionPreference = "Stop"

Set-Location $InstallDir
$venvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
$stateJson = & $venvPython manage.py shell -c "from core.models import ServerSyncState; import json; s=ServerSyncState.objects.filter(key='local_server').first(); print(json.dumps((s.value or {}) if s else {}))"
$state = $stateJson | ConvertFrom-Json

if (-not $state.update_manifest_url) {
    Write-Host "No update_manifest_url configured."
    exit 0
}

$currentVersionPath = Join-Path $InstallDir "VERSION"
$currentVersion = ""
if (Test-Path $currentVersionPath) {
    $currentVersion = (Get-Content $currentVersionPath -Raw).Trim()
}

$manifest = Invoke-RestMethod -Uri $state.update_manifest_url -UseBasicParsing
if ($manifest.version -eq $currentVersion) {
    Write-Host "DurielMedic Clinic Server is already up to date: $currentVersion"
    exit 0
}

$tempRoot = Join-Path $env:TEMP ("durielmedic-update-" + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $tempRoot | Out-Null
$zipPath = Join-Path $tempRoot "update.zip"
$extractPath = Join-Path $tempRoot "package"
$rollbackRoot = Join-Path $InstallDir "rollback"
$rollbackDir = Join-Path $rollbackRoot ("before-" + ($manifest.version -replace '[^a-zA-Z0-9_.-]', '-') + "-" + (Get-Date -Format "yyyyMMddHHmmss"))

Invoke-WebRequest -Uri $manifest.package_url -OutFile $zipPath -UseBasicParsing

if ($manifest.sha256) {
    $hash = (Get-FileHash $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $manifest.sha256.ToLowerInvariant()) {
        throw "Update package hash mismatch."
    }
}

Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force
$packageRoot = Join-Path $extractPath "durielmedic-clinic-server"
if (-not (Test-Path $packageRoot)) {
    $packageRoot = $extractPath
}

$preserve = @(".env", ".venv", "db.sqlite3", "media", "logs")

Stop-ScheduledTask -TaskName "DurielMedic Clinic Server" -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName "DurielMedic Sync Worker" -ErrorAction SilentlyContinue

try {
    if (-not (Test-Path $rollbackRoot)) {
        New-Item -ItemType Directory -Path $rollbackRoot | Out-Null
    }
    New-Item -ItemType Directory -Path $rollbackDir | Out-Null

    Get-ChildItem $InstallDir -Force | ForEach-Object {
        if (($preserve + @("rollback")) -contains $_.Name) {
            return
        }
        Copy-Item $_.FullName -Destination $rollbackDir -Recurse -Force
    }

    Get-ChildItem $packageRoot -Force | ForEach-Object {
        if ($preserve -contains $_.Name) {
            return
        }
        $target = Join-Path $InstallDir $_.Name
        if (Test-Path $target) {
            Remove-Item $target -Recurse -Force
        }
        Copy-Item $_.FullName -Destination $target -Recurse -Force
    }

    & $venvPython -m pip install -r requirements.txt
    & $venvPython manage.py migrate

    if ($manifest.version) {
        $manifest.version | Set-Content -Path $currentVersionPath -Encoding UTF8
    }
} catch {
    Write-Host "Update failed. Rolling back to previous version."

    Get-ChildItem $InstallDir -Force | ForEach-Object {
        if (($preserve + @("rollback")) -contains $_.Name) {
            return
        }
        Remove-Item $_.FullName -Recurse -Force
    }

    Get-ChildItem $rollbackDir -Force | ForEach-Object {
        Copy-Item $_.FullName -Destination $InstallDir -Recurse -Force
    }

    Start-ScheduledTask -TaskName "DurielMedic Clinic Server" -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName "DurielMedic Sync Worker" -ErrorAction SilentlyContinue
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    throw
}

Start-ScheduledTask -TaskName "DurielMedic Clinic Server" -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName "DurielMedic Sync Worker" -ErrorAction SilentlyContinue

Get-ChildItem $rollbackRoot -Directory | Sort-Object LastWriteTime -Descending | Select-Object -Skip 3 | Remove-Item -Recurse -Force
Remove-Item $tempRoot -Recurse -Force
Write-Host "DurielMedic Clinic Server updated to $($manifest.version)."
