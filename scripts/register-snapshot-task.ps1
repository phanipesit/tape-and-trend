# Registers the "TapeTrendSnapshot" scheduled task: records fired signals, scores open
# ones, and captures the day's FII/DII flows — whether or not the backend is running.
#
# WHY IT TRIGGERS ON LOGON AS WELL AS DAILY
# A wall-clock trigger assumes the machine is on at that time. This one is not: over
# 38 days exactly one run landed in the scheduled window, and there was a ten-day stretch
# (2026-08-16 to 08-26) with the laptop fully powered off. StartWhenAvailable helps but
# fires at most one catch-up per resume, and skipped two of them outright — 16 days were
# missed, and the FII/DII flows among them are unrecoverable because NSE publishes no
# history.
#
# So the primary trigger is now "whenever the machine is actually available", with the
# daily one kept as a backstop and moved to 20:30, matching when this machine is
# typically on. Both runs are cheap: the snapshot is idempotent via signal_outcomes'
# UNIQUE constraint, backfill re-derives rather than duplicates, and flows upsert.
#
# Waking the machine is not an option here — powercfg reports no S3 on this hardware,
# only Modern Standby and Hibernate, and nothing resumes a hibernated box on a timer.

# Without this the script happily prints its success message after Register-ScheduledTask
# has failed — which is exactly what it did on the first attempt at this change.
$ErrorActionPreference = "Stop"

$py = Join-Path $PSScriptRoot "..\backend\.venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "daily-snapshot.py"
if (-not (Test-Path $py))     { throw "no venv python at $py" }
if (-not (Test-Path $script)) { throw "no script at $script" }

$action = New-ScheduledTaskAction -Execute $py -Argument "`"$script`""

# A repeating trigger, NOT at-logon. The logon attempt was wrong: this machine resumes
# from hibernation with the user session intact, so no logon event occurs and the trigger
# never fired once in nine days despite several resumes. Repetition depends on no logon
# semantics at all — Task Scheduler simply runs it whenever the machine is on.
#
# Every 3 hours from 09:00. Extra runs are close to free: the snapshot is idempotent,
# mid-session symbols are skipped, and the backup exits early if today's dump exists.
$trigger = New-ScheduledTaskTrigger -Daily -At 09:00
$trigger.Repetition = (New-CimInstance -ClassName MSFT_TaskRepetitionPattern `
    -Namespace Root/Microsoft/Windows/TaskScheduler -ClientOnly `
    -Property @{ Interval = "PT3H"; Duration = "P1D"; StopAtDurationEnd = $false })
$triggers = @($trigger)

# ExecutionTimeLimit was PT20M. A catch-up run does a 15-session backfill across the
# whole universe before it even starts scoring, and being killed mid-write is worse than
# running long — PT2H is effectively "don't interfere".
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
# Not a parameter of New-ScheduledTaskSettingsSet on PowerShell 5.1 — assigned after.
# Matters here: the logon and daily triggers can otherwise overlap on a late evening.
$settings.MultipleInstances = 2   # 2 = IgnoreNew

Register-ScheduledTask -TaskName "TapeTrendSnapshot" -Action $action `
    -Trigger $triggers -Settings $settings -Force | Out-Null

Write-Output "Scheduled task 'TapeTrendSnapshot' registered: every 3h from 09:00."
Write-Output "Log: C:\users\phani\claude_code\files\signal-tracker.log"
Write-Output "Remove with: Unregister-ScheduledTask -TaskName TapeTrendSnapshot -Confirm:`$false"
