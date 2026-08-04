param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").ProviderPath,
    [string]$InnoCompiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    [string]$Version = "1.0.0",
    [string]$PackageBaseUrl = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path $ProjectRoot).ProviderPath
$distRoot = Join-Path $ProjectRoot "dist"
$stageDir = Join-Path $distRoot "durielmedic-clinic-server"

if (-not (Test-Path $distRoot)) {
    New-Item -ItemType Directory -Path $distRoot | Out-Null
}

if (Test-Path $stageDir) {
    Remove-Item $stageDir -Recurse -Force
}
New-Item -ItemType Directory -Path $stageDir | Out-Null

$excludeDirs = @(
    ".git",
    ".venv",
    "env",
    "venv",
    "myenv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "media",
    "logs"
)
$excludeFiles = @(
    ".env",
    "db.sqlite3",
    "OFFLINE*.md",
    "*.pyc",
    "*.pyo"
)

Get-ChildItem $ProjectRoot -Force | ForEach-Object {
    if ($excludeDirs -contains $_.Name) {
        return
    }
    $entry = $_
    $excludedFile = $excludeFiles | Where-Object { $entry.Name -like $_ }
    if (-not $entry.PSIsContainer -and $excludedFile) {
        return
    }
    Copy-Item $entry.FullName -Destination $stageDir -Recurse -Force
}

Get-ChildItem $stageDir -Recurse -Include *.pyc,*.pyo | Remove-Item -Force
Get-ChildItem $stageDir -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force

$versionPath = Join-Path $stageDir "VERSION"
$Version | Set-Content -Path $versionPath -Encoding UTF8

$zipPath = Join-Path $distRoot "durielmedic-clinic-server-$Version.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zipPath -Force
$sha256 = (Get-FileHash $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$packageUrl = if ($PackageBaseUrl) { "$($PackageBaseUrl.TrimEnd('/'))/durielmedic-clinic-server-$Version.zip" } else { "durielmedic-clinic-server-$Version.zip" }
$manifest = [ordered]@{
    version = $Version
    package_url = $packageUrl
    sha256 = $sha256
}
$manifest | ConvertTo-Json | Set-Content -Path (Join-Path $distRoot "update-manifest.json") -Encoding UTF8

if (-not (Test-Path $InnoCompiler)) {
    throw "Inno Setup compiler not found at $InnoCompiler"
}

& $InnoCompiler (Join-Path $PSScriptRoot "DurielMedicClinicServer.iss")
