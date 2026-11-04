# Ofelia files (copy into infrastructure)

These are copy-paste copies. Nothing here runs from this repo.

## 1. Script

Copy:

```
ofelia/scripts/api/sheet-data-automation-run-all.sh
  -> infrastructure/ofelia/scripts/api/sheet-data-automation-run-all.sh
```

The script runs `cacmai -> balco -> drag` through one API call and fails the
Ofelia job when the API returns non-200 or `"success": false`.

## 2. Ofelia job

Append:

```
ofelia/config.append.ini
  -> infrastructure/ofelia/config.ini
```

Schedule: `10:00`, `13:00`, `16:00` IST daily.

## 3. Environment

Add:

```
ofelia/env.append
  -> infrastructure/.env
```

`SHEET_DATA_API_KEY` must be the same value used by the app container
(`SHEET_DATA_API_KEY` in this repo's `.env`).

## 4. Compose service

The `ofelia` service has no `env_file`, so values in `.env` only reach it when
listed under its `environment:`. Add to the `ofelia` service in
`infrastructure/docker-compose.yml`:

```yaml
    environment:
      SHEET_DATA_SERVER: ${SHEET_DATA_SERVER}
      SHEET_DATA_API_KEY: ${SHEET_DATA_API_KEY}
```

## 5. Apply

```sh
cd infrastructure
docker compose up -d sheet-data-automation ofelia
docker compose logs -f ofelia
```

Verify the API directly:

```sh
curl -H "x-api-key: $SHEET_DATA_API_KEY" \
  http://sheet-data-automation:8000/api/v1/run-all
```

Then disable the old Windows Task Scheduler tasks after the first successful
Ofelia run.
