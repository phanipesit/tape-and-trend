# Registers the "TapeTrendMarketOpen" scheduled task: runs market-open-check.py
# shortly after the NSE bell and leaves a report in claude_code\files\.
#
# Scheduled outside Claude on purpose. A job scheduled inside a Claude session lives
# only in that session's memory and dies when it exits, so it silently never fires
# if you close the terminal. This one runs regardless.
#
# Default is one-time today at 09:22 IST — seven minutes after the 09:15 open, since
# at the bell there are no intraday bars yet. Pass -Weekdays to make it recurring
# Mon-Fri instead.

param([switch]$Weekdays)

$py = Join-Path $PSScriptRoot "..\backend\.venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "market-open-check.py"
if (-not (Test-Path $py))     { throw "no venv python at $py" }
if (-not (Test-Path $script)) { throw "no script at $script" }

$action = New-ScheduledTaskAction -Execute $py -Argument "`"$script`""
$trigger = if ($Weekdays) {
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 09:22
} else {
    New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddHours(9).AddMinutes(22)
}
# StartWhenAvailable so a machine that was asleep at 09:22 still produces the report.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "TapeTrendMarketOpen" -Action $action `
    -Trigger $trigger -Settings $settings -Force | Out-Null

$when = if ($Weekdays) { "weekdays at 09:22" } else { "once today at 09:22" }
Write-Output "Scheduled task 'TapeTrendMarketOpen' registered: $when."
Write-Output "Report lands in C:\users\phani\claude_code\files\market-open-<date>.md"
Write-Output "Remove with: Unregister-ScheduledTask -TaskName TapeTrendMarketOpen -Confirm:`$false"
