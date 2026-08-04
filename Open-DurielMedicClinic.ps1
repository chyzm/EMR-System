param(
    [int]$Port = 9000
)

$ErrorActionPreference = "SilentlyContinue"

Start-ScheduledTask -TaskName "DurielMedic Clinic Server"
Start-Sleep -Seconds 2
Start-Process "http://localhost:$Port"
