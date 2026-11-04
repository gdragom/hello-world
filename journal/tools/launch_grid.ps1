$ErrorActionPreference = "Stop"
$work = Join-Path $env:TEMP "ledger_grid_work"
New-Item -ItemType Directory -Path $work -Force | Out-Null
Remove-Item (Join-Path $work "*_rows.csv") -ErrorAction SilentlyContinue
Remove-Item (Join-Path $work "run.log") -ErrorAction SilentlyContinue
$wd = "c:\Users\user\OneDrive\hello-world\journal\tools"
$p = Start-Process -FilePath "python" `
  -ArgumentList @("-u", "grid_tv_custom_balance.py") `
  -WorkingDirectory $wd `
  -RedirectStandardOutput (Join-Path $work "stdout.txt") `
  -RedirectStandardError (Join-Path $work "stderr.txt") `
  -PassThru -WindowStyle Hidden
Set-Content -Path (Join-Path $work "pid.txt") -Value $p.Id
Write-Output "started pid=$($p.Id)"
