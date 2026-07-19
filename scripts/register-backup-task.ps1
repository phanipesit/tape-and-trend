# Registers (or refreshes) the daily "TapeTrendBackup" Windows scheduled task.
# Runs backup-db.ps1 every day at 17:00, or as soon as possible after the
# machine next wakes if it was off/asleep at that time.

$script = Join-Path $PSScriptRoot "backup-db.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 17:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
Register-ScheduledTask -TaskName "TapeTrendBackup" -Action $action `
    -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Output "Scheduled task 'TapeTrendBackup' registered: daily at 17:00 (runs on next wake if missed)."
