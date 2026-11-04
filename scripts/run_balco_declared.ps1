$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root -ErrorAction Stop

& py run_balco_declared.py @args
exit $LASTEXITCODE
