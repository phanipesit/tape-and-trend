# Registers (or refreshes) the "TapeTrendBackup" Windows scheduled task.
#
# Triggers at logon and daily at 20:45, for the same reason as the snapshot task: a
# wall-clock-only trigger landed exactly one run in the scheduled window across 38 days,
# because this machine is usually off in the evening. See register-snapshot-task.ps1 for
# the full diagnosis.
#
# backup-db.ps1 exits early when today's dump already exists, so the extra logon runs
# cost nothing — without that guard several logons a day would mean several 12MB
# pg_dumps a day.

# Without this the script prints success even when Register-ScheduledTask has failed.
$ErrorActionPreference = "Stop"

$script = Join-Path $PSScriptRoot "backup-db.ps1"
if (-not (Test-Path $script)) { throw "no script at $script" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""

$triggers = @(
    (New-ScheduledTaskTrigger -Daily -At 20:45),
    (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME)
)
# Later than the snapshot's logon delay so the dump captures that run's writes.
$triggers[1].Delay = "PT10M"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$settings.MultipleInstances = 2   # 2 = IgnoreNew; not a param on PowerShell 5.1

Register-ScheduledTask -TaskName "TapeTrendBackup" -Action $action `
    -Trigger $triggers -Settings $settings -Force | Out-Null

Write-Output "Scheduled task 'TapeTrendBackup' registered: at logon (+10 min) and daily 20:45."
Write-Output "Remove with: Unregister-ScheduledTask -TaskName TapeTrendBackup -Confirm:`$false"
