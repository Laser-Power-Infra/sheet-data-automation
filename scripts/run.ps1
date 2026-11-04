$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root -ErrorAction Stop

& py main.py @args
exit $LASTEXITCODE
