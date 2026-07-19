# Daily backup of the tapetrend PostgreSQL database.
# Reads DATABASE_URL from backend/.env, dumps to %USERPROFILE%\tape-and-trend-backups,
# and keeps the newest 14 dumps. Registered in Windows Task Scheduler as "TapeTrendBackup"
# (see README section in this folder or re-run scripts\register-backup-task.ps1).

$ErrorActionPreference = "Stop"

$repoRoot  = Split-Path -Parent $PSScriptRoot
$envFile   = Join-Path $repoRoot "backend\.env"
$backupDir = Join-Path $env:USERPROFILE "tape-and-trend-backups"
$pgDump    = "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"

# DATABASE_URL=postgresql+psycopg2://user:pass@host:port/dbname
$line = (Get-Content $envFile | Where-Object { $_ -match "^DATABASE_URL=" } | Select-Object -First 1)
if (-not $line) { throw "DATABASE_URL not found in $envFile" }
$url = $line -replace "^DATABASE_URL=", "" -replace "^postgresql\+psycopg2", "postgresql"
if ($url -notmatch "^postgresql://([^:]+):([^@]*)@([^:/]+):(\d+)/(.+)$") { throw "cannot parse DATABASE_URL" }
$user = $Matches[1]; $pass = $Matches[2]; $dbHost = $Matches[3]; $port = $Matches[4]; $db = $Matches[5]

New-Item -ItemType Directory -Force $backupDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd"
$out = Join-Path $backupDir "tapetrend-$stamp.sql"

$env:PGPASSWORD = $pass
& $pgDump -h $dbHost -p $port -U $user -d $db -f $out
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }
Remove-Item Env:\PGPASSWORD

# retention: keep newest 14
Get-ChildItem $backupDir -Filter "tapetrend-*.sql" |
    Sort-Object Name -Descending |
    Select-Object -Skip 14 |
    Remove-Item -Force

Write-Output "backup written: $out ($([math]::Round((Get-Item $out).Length / 1KB)) KB)"
