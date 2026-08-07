param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").ProviderPath,
    [string]$InnoCompiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    [string]$Version = "1.0.0",
    [string]$PackageBaseUrl = "",
    [switch]$ReuseDesktopExecutable
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path $ProjectRoot).ProviderPath
$distRoot = Join-Path $ProjectRoot "dist"
$stageDir = Join-Path $distRoot "durielmedic-clinic-server"
$desktopVersionPath = Join-Path $ProjectRoot "DESKTOP_VERSION"
$desktopBuildScript = Join-Path $PSScriptRoot "Build-DesktopApp.ps1"
$desktopExe = Join-Path $distRoot "DurielMedicClinicServer.exe"
$updaterSource = Join-Path $PSScriptRoot "Update-DurielMedicClinic.ps1"
$configureSource = Join-Path $PSScriptRoot "Configure-DurielMedicTasks.ps1"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# ---------------------------------------------------------
# Validate updater source before building the release.
# Prevent accidentally packaging an old updater.
# ---------------------------------------------------------

if (-not (Test-Path $updaterSource -PathType Leaf)) {
    throw "Release aborted: updater source not found at $updaterSource"
}

$updaterContent = Get-Content $updaterSource -Raw

if ($updaterContent -notmatch 'TimeoutSeconds\s*=\s*120') {
    throw "Release aborted: updater does not contain the 120-second startup timeout."
}

if ($updaterContent -notmatch 'Port \$Port is free') {
    throw "Release aborted: updater does not contain the port-release protection."
}

if ($updaterContent -notmatch 'Migration marker updated') {
    throw "Release aborted: updater does not contain the migration-marker fix."
}

Write-Host "Updater validation passed."


if (-not (Test-Path $distRoot)) {
    New-Item -ItemType Directory -Path $distRoot | Out-Null
}

# Build the executable first. The update ZIP must contain this exact executable;
# source-only ZIPs cannot update the frozen desktop application.
if ($ReuseDesktopExecutable) {
    if (-not (Test-Path $desktopExe -PathType Leaf)) {
        throw "Cannot reuse the desktop executable because $desktopExe does not exist."
    }
    $builtVersion = if (Test-Path $desktopVersionPath -PathType Leaf) {
        (Get-Content $desktopVersionPath -Raw).Trim()
    } else {
        ""
    }
    if ($builtVersion -ne $Version) {
        throw "Refusing to reuse desktop version $builtVersion for requested version $Version."
    }
} else {
    [System.IO.File]::WriteAllText($desktopVersionPath, $Version, $utf8NoBom)
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $desktopBuildScript -ProjectRoot $ProjectRoot -Version $Version
    if ($LASTEXITCODE -ne 0) {
        throw "Desktop build failed with exit code $LASTEXITCODE."
    }
}
if (-not (Test-Path $desktopExe -PathType Leaf)) {
    throw "Desktop executable not found at $desktopExe."
}

if (Test-Path $stageDir) {
    Remove-Item $stageDir -Recurse -Force
}
New-Item -ItemType Directory -Path (Join-Path $stageDir "updater") -Force | Out-Null
Copy-Item $desktopExe (Join-Path $stageDir "DurielMedicClinicServer.exe") -Force
Copy-Item $updaterSource (Join-Path $stageDir "updater\Update-DurielMedicClinic.ps1") -Force
Copy-Item $configureSource (Join-Path $stageDir "updater\Configure-DurielMedicTasks.ps1") -Force
[System.IO.File]::WriteAllText((Join-Path $stageDir "VERSION"), $Version, $utf8NoBom)

$zipPath = Join-Path $distRoot "durielmedic-clinic-server-$Version.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zipPath -Force
$sha256 = (Get-FileHash $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$packageUrl = if ($PackageBaseUrl) {
    "$($PackageBaseUrl.TrimEnd('/'))/durielmedic-clinic-server-$Version.zip"
} else {
    "durielmedic-clinic-server-$Version.zip"
}
$manifest = [ordered]@{
    version = $Version
    package_url = $packageUrl
    sha256 = $sha256
    package_type = "desktop-executable"
}
$manifestJson = $manifest | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $distRoot "update-manifest.json"), $manifestJson, $utf8NoBom)

# Fail the release build if the ZIP is not a packaged-desktop update. This
# catches the old source-only archive format before it is uploaded to clinics.
$validationDir = Join-Path $env:TEMP ("durielmedic-package-check-" + [guid]::NewGuid().ToString("N"))
try {
    Expand-Archive -Path $zipPath -DestinationPath $validationDir -Force
    foreach ($requiredRelativePath in @(
        "DurielMedicClinicServer.exe",
        "VERSION",
        "updater\Update-DurielMedicClinic.ps1",
        "updater\Configure-DurielMedicTasks.ps1"
    )) {
        if (-not (Test-Path (Join-Path $validationDir $requiredRelativePath) -PathType Leaf)) {
            throw "Update ZIP validation failed: $requiredRelativePath is missing."
        }
    }
    $validatedVersion = (Get-Content (Join-Path $validationDir "VERSION") -Raw).Trim()
    if ($validatedVersion -ne $Version) {
        throw "Update ZIP validation failed: package version is $validatedVersion, expected $Version."
    }
} finally {
    Remove-Item $validationDir -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path $InnoCompiler -PathType Leaf)) {
    throw "Inno Setup compiler not found at $InnoCompiler"
}
& $InnoCompiler "/DMyAppVersion=$Version" (Join-Path $PSScriptRoot "DurielMedicClinicServer.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
}

Write-Host "Installer: $(Join-Path $distRoot 'DurielMedic-Clinic-Server-Setup.exe')"
Write-Host "Update ZIP: $zipPath"
Write-Host "Manifest: $(Join-Path $distRoot 'update-manifest.json')"
