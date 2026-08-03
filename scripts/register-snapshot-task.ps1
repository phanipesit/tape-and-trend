# Registers the daily "TapeTrendSnapshot" scheduled task: records fired signals and
# scores open ones, whether or not the backend happens to be running.
#
# That independence is the entire point. The tracker used to live in main.py's
# background loop, so it only recorded on days uvicorn was up — five snapshot days
# across three weeks, which is not a series.
#
# 18:10 IST: after the 15:30 NSE close so the day's bars are final, and off the :00/:30
# marks. StartWhenAvailable means a machine asleep at 18:10 still runs it on next wake,
# and the task is idempotent so a late run costs nothing.

$py = Join-Path $PSScriptRoot "..\backend\.venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "daily-snapshot.py"
if (-not (Test-Path $py))     { throw "no venv python at $py" }
if (-not (Test-Path $script)) { throw "no script at $script" }

$action = New-ScheduledTaskAction -Execute $py -Argument "`"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 18:10
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
Register-ScheduledTask -TaskName "TapeTrendSnapshot" -Action $action `
    -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Output "Scheduled task 'TapeTrendSnapshot' registered: daily at 18:10 (runs on next wake if missed)."
Write-Output "Log: C:\users\phani\claude_code\files\signal-tracker.log"
Write-Output "Remove with: Unregister-ScheduledTask -TaskName TapeTrendSnapshot -Confirm:`$false"
