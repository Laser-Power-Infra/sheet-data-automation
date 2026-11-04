from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from ..archive.config import load_archive_config
from ..balco_declared.config import load_balco_declared_config
from ..cacmai_conductors.config import load_cacmai_config
from ..common.config import load_app_config
from ..common.errors import ConfigError, ParseError, ScrapeError, SheetError
from ..common.logging import setup_logging
from .auth import require_api_key
from .jobs import (
    JOB_ORDER,
    JobAlreadyRunningError,
    is_busy,
    last_results,
    run_all,
    run_single,
)
from .schemas import RunRequest, RunResponse

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging("api")
    LOGGER.info("sheet-data-automation API starting")
    yield
    LOGGER.info("sheet-data-automation API stopping")


app = FastAPI(
    title="sheet-data-automation",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(JobAlreadyRunningError)
async def _busy_handler(_, exc: JobAlreadyRunningError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"success": False, "error": str(exc)})


@app.exception_handler(ConfigError)
async def _config_handler(_, exc: ConfigError) -> JSONResponse:
    LOGGER.error("Configuration error: %s", exc)
    return JSONResponse(status_code=503, content={"success": False, "error": str(exc)})


@app.exception_handler(SheetError)
async def _sheet_handler(_, exc: SheetError) -> JSONResponse:
    LOGGER.error("Google Sheets error: %s", exc)
    return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.exception_handler(ScrapeError)
async def _scrape_handler(_, exc: ScrapeError) -> JSONResponse:
    LOGGER.error("Scrape error: %s", exc)
    return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.exception_handler(ParseError)
async def _parse_handler(_, exc: ParseError) -> JSONResponse:
    LOGGER.error("Parse error: %s", exc)
    return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.exception_handler(Exception)
async def _unexpected_handler(_, exc: Exception) -> JSONResponse:
    LOGGER.error(
        "Unhandled API error: %s",
        exc,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(status_code=500, content={"success": False, "error": "Internal error"})


def _config_status() -> tuple[bool, str | None]:
    try:
        load_app_config()
        load_cacmai_config()
        load_balco_declared_config()
        load_archive_config()
    except ConfigError as exc:
        return False, str(exc)
    return True, None


def _last_payload() -> dict[str, dict[str, object]]:
    return {name: result.model_dump() for name, result in last_results().items()}


@app.get("/health")
def health() -> JSONResponse:
    config_ok, config_error = _config_status()
    payload = {
        "status": "ok" if config_ok else "degraded",
        "config_ok": config_ok,
        "config_error": config_error,
        "busy": is_busy(),
        "last": _last_payload(),
    }
    return JSONResponse(status_code=200 if config_ok else 503, content=payload)


@app.get("/api/v1/status")
def status(_: None = Depends(require_api_key)) -> dict[str, object]:
    config_ok, config_error = _config_status()
    return {
        "success": True,
        "busy": is_busy(),
        "config_ok": config_ok,
        "config_error": config_error,
        "last": _last_payload(),
    }


def _require_job(job: str) -> None:
    if job not in JOB_ORDER:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job}")


@app.get("/api/v1/jobs/{job}")
def probe_job(job: str, _: None = Depends(require_api_key)) -> dict[str, object]:
    _require_job(job)
    return {
        "success": True,
        "auth": "ok",
        "job": job,
        "note": "POST to run the job.",
    }


@app.post("/api/v1/jobs/{job}")
def run_job(
    job: str,
    request: RunRequest | None = None,
    _: None = Depends(require_api_key),
) -> RunResponse:
    _require_job(job)
    if job != "balco" and request is not None and request.date_override is not None:
        raise HTTPException(
            status_code=422,
            detail="date_override is only supported for the balco job.",
        )
    return run_single(job, request)


@app.get("/api/v1/run-all")
def probe_all(_: None = Depends(require_api_key)) -> dict[str, object]:
    return {
        "success": True,
        "auth": "ok",
        "jobs": list(JOB_ORDER),
        "note": "POST to run all jobs in order.",
    }


@app.post("/api/v1/run-all")
def run_everything(
    request: RunRequest | None = None,
    _: None = Depends(require_api_key),
) -> RunResponse:
    return run_all(request)
