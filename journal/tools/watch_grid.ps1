$ErrorActionPreference = "Continue"
$work = Join-Path $env:TEMP "ledger_grid_work"
$wd = "c:\Users\user\OneDrive\hello-world\journal\tools"
$need = 576

function RowCount([string]$path) {
  if (-not (Test-Path $path)) { return 0 }
  # count lines minus header; avoid Import-Csv file lock
  $n = @(Get-Content -LiteralPath $path).Count
  if ($n -le 1) { return 0 }
  return ($n - 1)
}

while ($true) {
  $long = Join-Path $work "long_rows.csv"
  $short = Join-Path $work "short_rows.csv"
  $ln = RowCount $long
  $sn = RowCount $short
  if ($ln -ge $need -and $sn -ge $need) {
    Write-Output ("both complete long={0} short={1} - finalize" -f $ln, $sn)
    $p = Start-Process -FilePath "python" -ArgumentList @("-u", "grid_tv_custom_balance.py", "--resume") -WorkingDirectory $wd -Wait -PassThru -WindowStyle Hidden
    Write-Output ("finalize exit={0}" -f $p.ExitCode)
    break
  }
  $pidFile = Join-Path $work "pid.txt"
  $alive = $false
  if (Test-Path $pidFile) {
    $gridPid = [int](Get-Content $pidFile -Raw).Trim()
    $alive = $null -ne (Get-Process -Id $gridPid -ErrorAction SilentlyContinue)
  }
  if (-not $alive) {
    Write-Output ("python dead; resume long={0} short={1}" -f $ln, $sn)
    $p = Start-Process -FilePath "python" -ArgumentList @("-u", "grid_tv_custom_balance.py", "--resume") -WorkingDirectory $wd -RedirectStandardOutput (Join-Path $work "stdout.txt") -RedirectStandardError (Join-Path $work "stderr.txt") -PassThru -WindowStyle Hidden
    Set-Content -Path $pidFile -Value $p.Id
  } else {
    Write-Output ("running long={0} short={1}" -f $ln, $sn)
  }
  Start-Sleep -Seconds 60
}
