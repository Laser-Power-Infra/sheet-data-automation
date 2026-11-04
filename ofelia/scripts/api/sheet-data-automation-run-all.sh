#!/bin/sh
# Usage: sheet-data-automation-run-all.sh
# Runs CACMAI -> BALCO DECLARED -> linked drag sheets in one API call.
#
# Failure modes, all of which must fail the job:
#   - Non-200: wget itself exits non-zero, and `set -e` aborts the script.
#   - 200 whose body reports success=false: caught by the grep below.
#   - 401/503/409: wget exits non-zero.
#
# Env (set in the ofelia container, not committed):
#   SHEET_DATA_SERVER    base URL, e.g. http://sheet-data-automation:8000
#   SHEET_DATA_API_KEY   must match SHEET_DATA_API_KEY on the app
set -eu

: "${SHEET_DATA_SERVER:?SHEET_DATA_SERVER is not set in the ofelia container}"
: "${SHEET_DATA_API_KEY:?SHEET_DATA_API_KEY is not set in the ofelia container}"

url="${SHEET_DATA_SERVER}/api/v1/run-all"

# Cheap credential probe first: GET authenticates but does NOT run the jobs.
probe=$(wget -qO- -T 30 --header "x-api-key: ${SHEET_DATA_API_KEY}" "${url}" || true)
case "$probe" in
  *'"auth":"ok"'*) : ;;
  *)
    echo "ERROR: credential probe failed for $url"
    echo "$probe"
    exit 1
    ;;
esac

echo "POST $url (key length ${#SHEET_DATA_API_KEY})"
body=$(wget -qO- -T 3600 \
  --header 'Content-Type: application/json' \
  --header "x-api-key: ${SHEET_DATA_API_KEY}" \
  --post-data '{}' \
  "$url")

echo "$body"

if echo "$body" | grep -q '"success": *false'; then
  echo "ERROR: sheet-data-automation reported success=false"
  exit 1
fi

echo "OK: sheet-data-automation run-all completed"
