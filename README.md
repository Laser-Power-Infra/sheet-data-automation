# sheet-data-automation

Daily automation for the CACMAI Google Sheet tabs:

| Runner | Tab | What it fills |
| --- | --- | --- |
| `main.py` | `CACMAI CONDUCTORS` | NALCO/BALCO/Hindalco prices (`T:W`) and formulas (`X:AA`) |
| `run_balco_declared.py` | `BALCO DECLARED` | RBI USD rate (`E`) and LME Cash Offer (`C/R/X`) |
| `run_drag_sheets.py` | linked IEEMA/NALCO tabs | dates plus configured columns |

## CACMAI CONDUCTORS

| Column | Source | Field |
| --- | --- | --- |
| **A** | - | run date |
| **B** | copied from row above | `=CONCATENATE(MONTH(A),YEAR(A))` |
| **T** | NALCO | `ALUMINIUM INGOT IE07` |
| **U** | BALCO (first circular) | `CG 99 %` |
| **V** | Hindalco (first ready reckoner) | `CG Grade Ingot & Sow 99.5% (min) purity` |
| **W** | same BALCO circular | `EC 99.6% / EC 99.5% / CG 99.5%` (Vedanta row) |
| **X** | copied from row above | `=AVERAGE(T:W)` |
| **Y** | copied from row above | `=S - SUM(T:W)/4` |
| **Z** | copied from row above | `=SUM(T:W)/4 + $Y$1723 + 7000` |
| **AA** | copied from row above | `=Z(next row) + 7257 - 269` |

- Links are read from `T1`, `U1`, `V1`; `W1` (Vedanta login) is not used.
- Every run re-scrapes NALCO/BALCO/Hindalco. If a fetched value differs, it updates
  the cell; if the same, it leaves it.
- If a source fails or has no value:
  - keep today's existing value;
  - if today's cell is blank, carry the nearest previous value above.
- If `T:U:V:W` are complete but `B`/`X:AA` are missing, pull `B` and `X:AA` down
  without scraping.
- The previous row's `B`/`X:AA` are also checked and repaired every run.
- `B` and `X:AA` are copied with `copyPaste`; `B` is a separate copy range so the
  inserted/static columns between B and X are not overwritten.
- Refuses to append if the sheet is ahead of today; uses today's row if it exists.
- Missed dates (no run that day) are added before today's row by copying the row
  above (`A:AA`), so the IEEMA/NALCO VLOOKUPs never hit a missing date. Same in
  `BALCO DECLARED`, which also replaces the carried LME price (when LME reports that
  date) and the RBI rate for missed weekdays. CACMAI prices stay carried (sources only
  show the current circular). Limit: 366 days.
- If any source failed, the run exits `1` even when a previous value was carried.

## Drag linked sheets

Run this **after** `main.py` and `run_balco_declared.py`, because these tabs use
VLOOKUPs into `CACMAI CONDUCTORS` and `BALCO DECLARED`:

```powershell
py run_drag_sheets.py
```

It appends missing dates up to today and drags the configured columns:

| Tab | gid | Columns copied |
|---|---:|---|
| IEEMA PROV MCX | `1984490678` | every non-empty cell in the previous row, except `A` |
| IEEMA CABLES | `0` | `B, E, G` |
| IEEMA CONDUCTOR | `1178120759` | `B, D` |
| NALCO DECLARED | `1927552542` | `B:H`; `I` is left to the ARRAYFORMULA spill |

- `A` is always inserted as the date, not copied.
- The copy uses `copyPaste` (`PASTE_NORMAL`), so formulas adjust and static values
  and formats are copied.
- Existing formulas count as filled even if their linked value is currently blank
  (for example IEEMA PROV MCX `W`/`Z` before BALCO has the next row).
- If today's row already exists, only blank configured cells are filled; the date is
  never duplicated.
- `IEEMA CABLES` currently has protected ranges (entire sheet plus columns A/B).
  The service account must be added as an editor to those protections, otherwise
  the date write fails with "protected cell".

## Circular archive + Google upload

CACMAI saves each downloaded circular PDF to `W:`:

| Source | Folder | Filename |
| --- | --- | --- |
| BALCO | `W:\ALU price history\Balco2\Oct 2026` | `<stem> Balco.pdf` |
| Hindalco | `W:\ALU price history\HINDALCO2\Oct` (2027+: `Jan 2027`) | `<stem> Hindalco.pdf` |
| NALCO | `W:\ALU price history\NALCO\2026-27\Oct` | `<stem> Nalco.pdf` |

- NALCO uses the financial-year folder (April to March): Oct 2026 is `2026-27`, April 2027 is `2027-28`.
- A new month or year folder is created automatically when the first PDF of that month arrives.
  `HINDALCO2` keeps its old month-only names for 2026; from Jan 2027 it uses `Jan 2027` like Balco2.
- A PDF is saved only if its SHA-256 is not already in the month folder.
- Same filename with different content is saved as `... (2).pdf`.

### Upload webhook (replaces the Google Form)
Google Forms file uploads need a signed-in browser and the Google Picker, which made
browser automation fragile. Instead, a small Apps Script web app
(`apps_script/Code.gs`) receives the PDF over HTTPS, saves it to a Drive folder and
appends a row (Timestamp, Circular Type, Drive link, Select Date) to the responses sheet.

One-time setup (as `minmoy.dholey@laserpowerinfra.com`, who owns the upload folder):
1. Open https://script.google.com, create a project, paste `apps_script/Code.gs`.
2. Project Settings > Script Properties:

   | Name | Value |
   | --- | --- |
   | `WEBHOOK_TOKEN` | any long random string (`py -c "import secrets; print(secrets.token_urlsafe(32))"`) |
   | `UPLOAD_FOLDER_ID` | `1f6SHKc1CQCkwFjnaZ5oVmHRPFf29UODBYEuitBCbGxNJFIV3-Xy8ae8JNnXC6j3K0_8zvEhO` ("Upload Circular (File responses)") |
   | `RESPONSE_SHEET_ID` | `1qATwj8rCRpyzpto_-ErKEbjKrEVEfAp0DLGJE7K47Go` |
   | `RESPONSE_TAB` | `Form Responses 3` |
3. Deploy > New deployment > Web app: Execute as **Me**, Who has access **Anyone**.
   Authorize when asked.
4. Put the `/exec` URL and the token in `.env`:
   `FORM_WEBHOOK_URL=...`, `FORM_WEBHOOK_TOKEN=...`.

Values sent:
- Circular Type: `Nalco`, `Balco`, or `Hindalco` (Vedanta is skipped; BALCO covers it)
- PDF: the file already saved to `W:`
- Select Date: the circular's own date (same as the old form history)

Vedanta has no upload of its own: its price comes from the BALCO PDF, which is uploaded once as `Balco`.
Only a PDF that is new (SHA-256 not already in the month folder) is saved and uploaded.

Each entry in `state/archive_state.json` starts `pending`. Every CACMAI run retries all
pending entries first. After `FORM_MAX_ATTEMPTS` (default 10) failures an entry becomes
`failed`; set it back to `pending` to retry. If the webhook is not configured, files are
still saved and stay pending. Paths are stored relative to `ARCHIVE_ROOT`, so the same
state works on Windows and in Docker. Pre-existing W: files are never backfilled.

## FastAPI service

The three jobs are exposed by one FastAPI container. `run-all` runs them in order
(`cacmai` -> `balco` -> `drag`).

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | health/readiness, no auth |
| `GET` | `/api/v1/jobs/{job}` | credential probe only |
| `POST` | `/api/v1/jobs/{job}` | run one job (`cacmai`, `balco`, `drag`) |
| `GET` | `/api/v1/run-all` | credential probe only |
| `POST` | `/api/v1/run-all` | run all three in order |
| `GET` | `/api/v1/status` | last run result per job |

Requests need `x-api-key: $SHEET_DATA_API_KEY`. A missing server key returns `503`,
a wrong key `401`, an already-running job `409`. Job failures return HTTP `200`
with `"success": false` and per-job `failures`.

```powershell
curl -H "x-api-key: $env:SHEET_DATA_API_KEY" http://localhost:8000/api/v1/run-all
curl -X POST -H "x-api-key: $env:SHEET_DATA_API_KEY" `
  -H "Content-Type: application/json" -d '{\"dry_run\": true}' `
  http://localhost:8000/api/v1/run-all
```

Local:
```powershell
py run_api.py
```

## Docker (Windows Docker Desktop)

### Deploy (CI/CD)

Pushing to `main` runs `.github/workflows/deploy.yml`:

1. **build-and-push** (GitHub-hosted): builds the image and pushes
   `ghcr.io/laser-power-infra/sheet-data-automation:latest` and `:<short_sha>`.
2. **deploy** (self-hosted runner on the server): copies `docker-compose.yml` into
   `D:\sheet-data-automation`, then `docker compose pull` + `docker compose up -d`,
   prunes old images (keeps the newest two) and waits for `/health` to return 200.

`docker-compose.yml` uses the GHCR image (`${APP_VERSION:-latest}`); it no longer
builds locally. `.env`, `state/`, `logs/` and the external `infrastructure_condutor`
volume (mounted at `/mnt/alu`) live on the server and are not touched by the deploy.

Manual redeploy on the server:
```powershell
cd D:\sheet-data-automation
docker compose pull sheet-data-automation
docker compose up -d --no-deps sheet-data-automation
curl http://localhost:8000/health
```

Local image build (bypassing GHCR):
```powershell
docker build -t ghcr.io/laser-power-infra/sheet-data-automation:latest .
docker compose up -d
```

The API uses one uvicorn worker and one container replica; do not scale it.

CLI jobs still work through the same image:
```powershell
docker compose run --rm sheet-data-automation python main.py
docker compose run --rm sheet-data-automation python run_balco_declared.py
docker compose run --rm sheet-data-automation python run_drag_sheets.py
```

## Setup

```powershell
py -m pip install gspread google-auth pypdf python-dotenv playwright fastapi uvicorn
py -m playwright install chromium
Copy-Item .env.example .env
```

Fill `.env` with the service-account email/private key, `SHEET_DATA_API_KEY`, and share
the sheet with the service account as **Editor**.

## Run

```powershell
py run_api.py               # FastAPI service on :8000
```

CLI entry points remain for local runs:

```powershell
py main.py                  # CACMAI CONDUCTORS
py run_balco_declared.py    # BALCO DECLARED
py run_drag_sheets.py       # linked IEEMA/NALCO tabs
```

Run them in that order; the drag step depends on the first two.

Constants at the top of each CLI entry file control behavior:

```python
DRY_RUN = False
HEADLESS = True
```

`run_balco_declared.py` also has:

```python
DATE_OVERRIDE: str | None = None  # e.g. "2026-10-21"
```

Logs go to the console and to rotating files under `logs/`.

### One-time circular import

`run_cacmai_circular_import.py` imports the historical tables from a CACMAI PDF:

```powershell
py run_cacmai_circular_import.py            # dry run, prints planned cells
py run_cacmai_circular_import.py --apply    # writes + saves a backup in state/backups/
```

It fills `C:E`, `O:S`, `AM:AQ`, and `AS/AT/AV` for every calendar date between the
PDF's first and last date, carrying the previous value on dates the circular skips.
It does not append rows and leaves `AR`/`AU` untouched.

## Project structure

```
main.py                     # CACMAI entry point
run_balco_declared.py       # BALCO DECLARED entry point
run_drag_sheets.py          # linked IEEMA/NALCO drag entry point
run_api.py                  # FastAPI entry point
run_cacmai_circular_import.py  # one-time historical PDF import
src/sheet_data_automation/
  api/                      # FastAPI app, auth, job runner, schemas
  common/                   # browser, config, errors, retry, logging, Google helpers, PDF text
  cacmai_conductors/        # nalco.py, balco.py, hindalco.py, formulas.py, sheet.py, runner.py
  balco_declared/           # rbi.py, lme.py, sheet.py, runner.py, config.py
  drag_sheets/              # config.py, sheet.py, runner.py
  oneoff/                   # historical circular import
scripts/                    # legacy Task Scheduler launchers
tests/
```

## Tests and lint

```powershell
py -m pytest
py -m ruff check .
```

### Local note (Windows App Control)

On this machine an Application Control policy blocks `python.exe` inside `.venv`, so
`uv run` cannot start. Use the installed launcher (`py`) and the root entry files; no
`PYTHONPATH` or installation is required.

## Scheduling (Ofelia)

Production scheduling lives in the `infrastructure` repo, not this one. Copy-paste
files and instructions are in [`ofelia/README.md`](ofelia/README.md).

- `infrastructure/ofelia/scripts/api/sheet-data-automation-run-all.sh` calls
  `POST /api/v1/run-all` with `x-api-key`.
- `infrastructure/ofelia/config.ini` runs it daily at **10:00, 13:00 and 16:00 IST**
  (`0 0 10,13,16 * * *`, `no-overlap = true`).
- Ofelia needs `SHEET_DATA_SERVER` and `SHEET_DATA_API_KEY` in its container env.

The API also enforces a single run at a time, so a manual call cannot overlap the
scheduled run. A failed job makes the script exit `1` so the Ofelia job fails.

The legacy Windows Task Scheduler scripts under `scripts/` and the three tasks can be
disabled after the Ofelia job has run successfully.
