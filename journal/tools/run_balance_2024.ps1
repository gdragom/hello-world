$ErrorActionPreference = "Stop"
$wd = "c:\Users\user\OneDrive\hello-world\journal\tools"
$env:LEDGER_SEARCH_FROM = "2024-01-01"
$env:LEDGER_SEARCH_TO = "2024-12-31"
$env:LEDGER_HOLDOUT_FROM = "2025-01-01"
Set-Location $wd
foreach ($side in @("long", "short")) {
  Write-Output "=== grid $side ==="
  python -u "run_$side.py" grid --tag y2024
}
