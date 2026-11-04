$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root -ErrorAction Stop

& py run_drag_sheets.py @args
exit $LASTEXITCODE
