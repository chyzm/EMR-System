param(
    [string]$InstallDir = (Split-Path $PSScriptRoot -Parent),
    [int]$Port = 9000,
    [string]$ManifestUrl = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$InstallDir = [System.IO.Path]::GetFullPath($InstallDir)
$appExe = Join-Path $InstallDir "DurielMedicClinicServer.exe"
$configureScript = Join-Path $InstallDir "updater\Configure-DurielMedicTasks.ps1"
$versionPath = Join-Path $InstallDir "VERSION"
$runtimeRoot = Join-Path $env:ProgramData "DurielMedicClinicServer\runtime"
$dataRoot = Split-Path $runtimeRoot -Parent
$logsRoot = Join-Path $runtimeRoot "logs"
$rollbackRoot = Join-Path $dataRoot "rollback"
$serverTaskName = "DurielMedic Clinic Server"
$syncTaskName = "DurielMedic Sync Worker"
$syncPassLock = Join-Path $runtimeRoot "sync-worker.lock"
$syncOwnerLock = Join-Path $runtimeRoot "sync-worker-owner.lock"

New-Item -ItemType Directory -Path $logsRoot -Force | Out-Null
New-Item -ItemType Directory -Path $rollbackRoot -Force | Out-Null

$logPath = Join-Path $logsRoot "updater.log"
Start-Transcript -Path $logPath -Append | Out-Null

$mutex = New-Object System.Threading.Mutex($false, "Global\DurielMedicClinicUpdater")
$hasMutex = $false
$tempRoot = $null


function Invoke-CheckedExecutable(
    [string]$Executable,
    [string[]]$Arguments
) {
    # DurielMedicClinicServer.exe is built as a Windows GUI-subsystem executable.
    # Start-Process -Wait gives us a reliable exit code for management commands.
    $process = Start-Process `
        -FilePath $Executable `
        -ArgumentList $Arguments `
        -WorkingDirectory $InstallDir `
        -Wait `
        -PassThru

    if ($process.ExitCode -ne 0) {
        throw "$Executable failed with exit code $($process.ExitCode)."
    }
}


function Get-PortListener {
    try {
        return Get-NetTCPConnection `
            -LocalPort $Port `
            -State Listen `
            -ErrorAction SilentlyContinue
    }
    catch {
        return $null
    }
}



function Remove-SyncWorkerLocks {
    Remove-Item $syncPassLock -Force -ErrorAction SilentlyContinue
    Remove-Item $syncOwnerLock -Force -ErrorAction SilentlyContinue
    Write-Host "Sync worker locks cleared."
}


function Stop-DurielMedicProcesses {
    Write-Host "Stopping DurielMedic background services..."

    Stop-ScheduledTask -TaskName $serverTaskName -ErrorAction SilentlyContinue
    Stop-ScheduledTask -TaskName $syncTaskName -ErrorAction SilentlyContinue

    Start-Sleep -Seconds 2

    # First terminate the known packaged executable only when it exists.
    $knownProcesses = Get-Process -Name "DurielMedicClinicServer" -ErrorAction SilentlyContinue
    if ($knownProcesses) {
        try {
            & taskkill.exe /F /IM "DurielMedicClinicServer.exe" 2>$null | Out-Null
        }
        catch {
            # Remaining processes are handled by the CIM cleanup below.
        }
    }

    # Catch any remaining packaged DurielMedic processes.
    try {
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -eq "DurielMedicClinicServer.exe"
            } |
            ForEach-Object {
                Write-Host "Stopping remaining DurielMedic process PID=$($_.ProcessId)"
                Stop-Process `
                    -Id $_.ProcessId `
                    -Force `
                    -ErrorAction SilentlyContinue
            }
    }
    catch {
        Write-Warning "Unable to enumerate one or more DurielMedic processes: $_"
    }

    # Do not touch the installation until the old server has really released
    # the clinic port.
    $deadline = (Get-Date).AddSeconds(30)

    while ((Get-Date) -lt $deadline) {
        $listener = Get-PortListener

        if (-not $listener) {
            Write-Host "Port $Port is free."
            # All DurielMedic processes are stopped at this point, so any
            # remaining sync lock can only be stale.
            Remove-SyncWorkerLocks
            return
        }

        Write-Host "Waiting for port $Port to be released..."
        Start-Sleep -Seconds 1
    }

    throw "Unable to stop the existing DurielMedic server. Port $Port is still in use."
}


function Test-IsNewerVersion(
    [string]$Candidate,
    [string]$Current
) {
    if (-not $Current) {
        return $true
    }

    try {
        return ([version]$Candidate -gt [version]$Current)
    }
    catch {
        return (
            [string]::Compare(
                $Candidate,
                $Current,
                [StringComparison]::OrdinalIgnoreCase
            ) -gt 0
        )
    }
}


function Wait-ForClinicServer(
    [int]$TimeoutSeconds = 120
) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        $client = New-Object System.Net.Sockets.TcpClient

        try {
            $async = $client.BeginConnect(
                "127.0.0.1",
                $Port,
                $null,
                $null
            )

            if (
                $async.AsyncWaitHandle.WaitOne(1000) -and
                $client.Connected
            ) {
                $client.EndConnect($async)
                return $true
            }
        }
        catch {
            # Server is still starting.
        }
        finally {
            $client.Close()
        }

        Start-Sleep -Milliseconds 500
    }

    return $false
}


function Start-DurielMedicTasks {
    Write-Host "Starting DurielMedic clinic server..."

    Start-ScheduledTask `
        -TaskName $serverTaskName `
        -ErrorAction Stop

    if (-not (Wait-ForClinicServer)) {
        $launcherLog = Join-Path $logsRoot "launcher.log"

        if (Test-Path $launcherLog -PathType Leaf) {
            Write-Warning "Clinic server failed to become ready."
            Write-Warning "Last launcher messages:"

            Get-Content $launcherLog -Tail 40 |
                ForEach-Object {
                    Write-Warning $_
                }
        }

        throw "Clinic server did not become ready on port $Port."
    }

    Write-Host "Clinic server is ready on port $Port."

    Start-ScheduledTask `
        -TaskName $syncTaskName `
        -ErrorAction Stop

    Write-Host "DurielMedic sync worker started."
}


function Get-ConfiguredManifestUrl(
    [string]$ConfigOutputPath
) {
    if ($ManifestUrl) {
        return $ManifestUrl
    }

    Invoke-CheckedExecutable `
        $appExe `
        @(
            "--manage",
            "local_update_config",
            "--output",
            $ConfigOutputPath
        )

    if (-not (Test-Path $ConfigOutputPath -PathType Leaf)) {
        throw "Clinic server did not produce updater configuration."
    }

    $config = Get-Content $ConfigOutputPath -Raw | ConvertFrom-Json

    if (-not $config.activated -or $config.role -ne "local") {
        throw "Clinic server is not activated for local sync."
    }

    return [string]$config.update_manifest_url
}


try {
    $hasMutex = $mutex.WaitOne(0)

    if (-not $hasMutex) {
        Write-Host "Another DurielMedic updater is already running."
        exit 0
    }

    if (-not (Test-Path $appExe -PathType Leaf)) {
        throw "Desktop executable not found at $appExe"
    }

    $tempRoot = Join-Path `
        $env:TEMP `
        ("durielmedic-update-" + [guid]::NewGuid().ToString("N"))

    $extractPath = Join-Path $tempRoot "package"
    $zipPath = Join-Path $tempRoot "update.zip"
    $configPath = Join-Path $tempRoot "update-config.json"

    New-Item `
        -ItemType Directory `
        -Path $tempRoot `
        -Force |
        Out-Null

    $resolvedManifestUrl = Get-ConfiguredManifestUrl $configPath

    if (-not $resolvedManifestUrl) {
        Write-Host "No update manifest URL is configured for this clinic."
        exit 0
    }

    $manifestUri = [uri]$resolvedManifestUrl

    if ($manifestUri.Scheme -ne "https") {
        throw "The update manifest must use HTTPS."
    }

    Write-Host "Checking for DurielMedic updates..."

    $manifest = Invoke-RestMethod `
        -Uri $manifestUri.AbsoluteUri `
        -UseBasicParsing

    if (
        -not $manifest.version -or
        -not $manifest.package_url -or
        -not $manifest.sha256
    ) {
        throw "Update manifest must contain version, package_url, and sha256."
    }

    $packageUri = [uri]$manifest.package_url

    if ($packageUri.Scheme -ne "https") {
        throw "The update package must use HTTPS."
    }

    if (
        [string]$manifest.sha256 -notmatch '^[a-fA-F0-9]{64}$'
    ) {
        throw "Update manifest contains an invalid SHA-256 value."
    }

    $currentVersion = ""

    if (Test-Path $versionPath -PathType Leaf) {
        $currentVersion = (
            Get-Content $versionPath -Raw
        ).Trim()
    }

    $availableVersion = ([string]$manifest.version).Trim()

    if (
        -not $Force -and
        -not (
            Test-IsNewerVersion `
                $availableVersion `
                $currentVersion
        )
    ) {
        Write-Host (
            "DurielMedic Clinic Server is up to date. " +
            "Installed=$currentVersion Available=$availableVersion"
        )
        exit 0
    }

    Write-Host "Downloading DurielMedic Clinic Server $availableVersion..."

    Invoke-WebRequest `
        -Uri $packageUri.AbsoluteUri `
        -OutFile $zipPath `
        -UseBasicParsing

    $actualHash = (
        Get-FileHash $zipPath -Algorithm SHA256
    ).Hash.ToLowerInvariant()

    if (
        $actualHash -ne
        ([string]$manifest.sha256).ToLowerInvariant()
    ) {
        throw "Update package hash mismatch."
    }

    Write-Host "Update package verified."

    Expand-Archive `
        -Path $zipPath `
        -DestinationPath $extractPath `
        -Force

    $packageRoot = Join-Path `
        $extractPath `
        "durielmedic-clinic-server"

    if (-not (Test-Path $packageRoot -PathType Container)) {
        $packageRoot = $extractPath
    }

    $packageExe = Join-Path `
        $packageRoot `
        "DurielMedicClinicServer.exe"

    $packageVersionPath = Join-Path `
        $packageRoot `
        "VERSION"

    $packageConfigure = Join-Path `
        $packageRoot `
        "updater\Configure-DurielMedicTasks.ps1"

    $packageUpdater = Join-Path `
        $packageRoot `
        "updater\Update-DurielMedicClinic.ps1"

    foreach (
        $requiredPath in @(
            $packageExe,
            $packageVersionPath,
            $packageConfigure,
            $packageUpdater
        )
    ) {
        if (-not (Test-Path $requiredPath -PathType Leaf)) {
            throw "Update package is incomplete: $requiredPath is missing."
        }
    }

    $packageVersion = (
        Get-Content $packageVersionPath -Raw
    ).Trim()

    if ($packageVersion -ne $availableVersion) {
        throw (
            "Package version $packageVersion does not match " +
            "manifest version $availableVersion."
        )
    }

    Write-Host "Preparing rollback snapshot..."

    $safeCurrentVersion = (
        $currentVersion -replace '[^a-zA-Z0-9_.-]', '-'
    )

    if (-not $safeCurrentVersion) {
        $safeCurrentVersion = "unknown"
    }

    $rollbackDir = Join-Path `
        $rollbackRoot `
        (
            "before-" +
            $safeCurrentVersion +
            "-" +
            (Get-Date -Format "yyyyMMddHHmmss")
        )

    $rollbackAppDir = Join-Path $rollbackDir "app"
    $rollbackDataDir = Join-Path $rollbackDir "data"

    New-Item `
        -ItemType Directory `
        -Path $rollbackAppDir `
        -Force |
        Out-Null

    New-Item `
        -ItemType Directory `
        -Path $rollbackDataDir `
        -Force |
        Out-Null

    # IMPORTANT:
    # Stop the old server and prove that port 9000 is free BEFORE
    # backing up/replacing application files.
    Stop-DurielMedicProcesses

    Get-ChildItem $InstallDir -Force |
        ForEach-Object {
            Copy-Item `
                $_.FullName `
                -Destination $rollbackAppDir `
                -Recurse `
                -Force
        }

    $databasePath = Join-Path `
        $runtimeRoot `
        "db.sqlite3"

    if (Test-Path $databasePath -PathType Leaf) {
        Copy-Item `
            $databasePath `
            (Join-Path $rollbackDataDir "db.sqlite3") `
            -Force
    }

    try {
        Write-Host "Installing DurielMedic $packageVersion..."

        Get-ChildItem $packageRoot -Force |
            ForEach-Object {
                $target = Join-Path $InstallDir $_.Name

                if (Test-Path $target) {
                    Remove-Item `
                        $target `
                        -Recurse `
                        -Force
                }

                Copy-Item `
                    $_.FullName `
                    -Destination $target `
                    -Recurse `
                    -Force
            }

        # At this point $appExe now points to the newly installed executable.
        Write-Host "Running database migrations..."

        Invoke-CheckedExecutable `
            $appExe `
            @(
                "--manage",
                "migrate",
                "--noinput"
            )

        Write-Host "Running Django system checks..."

        Invoke-CheckedExecutable `
            $appExe `
            @(
                "--manage",
                "check"
            )

        # The updater has already migrated this release successfully.
        # Write the exact package version, rather than relying on an
        # older runtime version marker.
        $migratedVersionPath = Join-Path `
            $runtimeRoot `
            ".migrated-version"

        [System.IO.File]::WriteAllText(
            $migratedVersionPath,
            $packageVersion,
            (New-Object System.Text.UTF8Encoding($false))
        )

        Write-Host "Migration marker updated to $packageVersion."

        # Use the NEW configure script that was just installed.
        $configureScript = Join-Path `
            $InstallDir `
            "updater\Configure-DurielMedicTasks.ps1"

        & $configureScript `
            -InstallDir $InstallDir `
            -Port $Port

        Start-DurielMedicTasks
    }
    catch {
        $updateError = $_

        Write-Warning (
            "Update failed. Restoring application and clinic database."
        )

        Stop-DurielMedicProcesses

        Get-ChildItem $InstallDir -Force |
            Remove-Item `
                -Recurse `
                -Force

        Get-ChildItem $rollbackAppDir -Force |
            ForEach-Object {
                Copy-Item `
                    $_.FullName `
                    -Destination $InstallDir `
                    -Recurse `
                    -Force
            }

        $databaseBackup = Join-Path `
            $rollbackDataDir `
            "db.sqlite3"

        if (Test-Path $databaseBackup -PathType Leaf) {
            Remove-Item `
                "$databasePath-wal", `
                "$databasePath-shm" `
                -Force `
                -ErrorAction SilentlyContinue

            Copy-Item `
                $databaseBackup `
                $databasePath `
                -Force
        }

        $restoredConfigure = Join-Path `
            $InstallDir `
            "updater\Configure-DurielMedicTasks.ps1"

        if (Test-Path $restoredConfigure -PathType Leaf) {
            & $restoredConfigure `
                -InstallDir $InstallDir `
                -Port $Port

            try {
                Start-DurielMedicTasks
                Write-Host "Rollback completed and previous version restarted."
            }
            catch {
                Write-Warning (
                    "Rollback files were restored, but the previous " +
                    "DurielMedic server could not be restarted automatically: $_"
                )
            }
        }

        throw $updateError
    }

    # Keep only the three newest rollback snapshots.
    Get-ChildItem `
        $rollbackRoot `
        -Directory `
        -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 3 |
        Remove-Item -Recurse -Force

    Write-Host (
        "DurielMedic Clinic Server updated successfully to " +
        "$packageVersion."
    )
}
finally {
    if (
        $tempRoot -and
        (Test-Path $tempRoot)
    ) {
        Remove-Item `
            $tempRoot `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }

    if ($hasMutex) {
        $mutex.ReleaseMutex()
    }

    $mutex.Dispose()

    try {
        Stop-Transcript | Out-Null
    }
    catch {
    }
}
