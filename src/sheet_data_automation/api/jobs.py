from __future__ import annotations

import datetime as dt
import logging
import os
import secrets
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

from ..balco_declared.runner import run as balco_run
from ..cacmai_conductors.runner import run as cacmai_run
from ..common.result import RunResult
from ..drag_sheets.runner import run as drag_run
from .schemas import JobRunResult, RunRequest, RunResponse

LOGGER = logging.getLogger(__name__)

JOB_ORDER = ("cacmai", "balco", "drag")

_lock = threading.Lock()
LAST_RESULTS: dict[str, JobRunResult] = {}


class JobAlreadyRunningError(RuntimeError):
    pass


def is_busy() -> bool:
    return _lock.locked()


def last_results() -> dict[str, JobRunResult]:
    return dict(LAST_RESULTS)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


@contextmanager
def exclusive() -> Iterator[None]:
    if not _lock.acquire(blocking=False):
        raise JobAlreadyRunningError("Another run is already in progress.")
    try:
        yield
    finally:
        _lock.release()


def _run_one(name: str, request: RunRequest | None) -> JobRunResult:
    started = time.monotonic()
    dry_run = (
        request.dry_run
        if request is not None and request.dry_run is not None
        else _env_bool("DRY_RUN", False)
    )
    headless = _env_bool("HEADLESS", True)

    LOGGER.info("Starting job %s (dry_run=%s, headless=%s)", name, dry_run, headless)
    try:
        if name == "cacmai":
            result = cacmai_run(dry_run=dry_run, headless=headless)
        elif name == "balco":
            result = balco_run(
                dry_run=dry_run,
                headless=headless,
                date_override=request.date_override if request is not None else None,
            )
        elif name == "drag":
            result = drag_run(dry_run=dry_run)
        else:
            raise ValueError(f"Unknown job: {name}")
    except Exception:
        LOGGER.exception("Job %s crashed", name)
        raise

    elapsed = time.monotonic() - started
    job = _to_job_result(result, elapsed)
    LAST_RESULTS[name] = job
    LOGGER.info(
        "Finished job %s: success=%s exit_code=%s failures=%s (%.1fs)",
        name,
        job.success,
        job.exit_code,
        job.failures,
        elapsed,
    )
    return job


def _to_job_result(result: RunResult, elapsed: float) -> JobRunResult:
    return JobRunResult(
        name=result.name,
        success=result.success,
        exit_code=result.exit_code,
        failures=list(result.failures),
        duration_seconds=round(elapsed, 3),
    )


def run_single(name: str, request: RunRequest | None = None) -> RunResponse:
    run_id = _new_run_id()
    started_at = _now()
    started = time.monotonic()
    LOGGER.info("run_id=%s job=%s starting", run_id, name)
    try:
        with exclusive():
            job = _run_one(name, request)
    except JobAlreadyRunningError:
        raise
    except Exception as exc:
        failed = JobRunResult(
            name=name,
            success=False,
            exit_code=1,
            failures=[str(exc)],
            duration_seconds=round(time.monotonic() - started, 3),
        )
        LAST_RESULTS[name] = failed
        raise
    return _response([job], run_id, started_at, time.monotonic() - started)


def run_all(request: RunRequest | None = None) -> RunResponse:
    run_id = _new_run_id()
    started_at = _now()
    started = time.monotonic()
    LOGGER.info("run_id=%s run-all starting", run_id)
    jobs: list[JobRunResult] = []
    with exclusive():
        for name in JOB_ORDER:
            try:
                jobs.append(_run_one(name, request))
            except Exception as exc:
                LOGGER.exception("Job %s failed with an unexpected error", name)
                failed = JobRunResult(
                    name=name,
                    success=False,
                    exit_code=1,
                    failures=[str(exc)],
                    duration_seconds=0.0,
                )
                LAST_RESULTS[name] = failed
                jobs.append(failed)
    return _response(jobs, run_id, started_at, time.monotonic() - started)


def _response(
    jobs: list[JobRunResult],
    run_id: str,
    started_at: str,
    elapsed: float,
) -> RunResponse:
    success = all(job.success for job in jobs)
    if success:
        status = "success"
    elif any(job.success for job in jobs):
        status = "partial"
    else:
        status = "failed"
    response = RunResponse(
        success=success,
        status=status,
        run_id=run_id,
        started_at=started_at,
        duration_seconds=round(elapsed, 3),
        jobs=jobs,
        error=None if success else "; ".join(
            f"{job.name}: {', '.join(job.failures)}" for job in jobs if not job.success
        ),
    )
    LOGGER.info(
        "run_id=%s finished status=%s success=%s (%.1fs)",
        run_id,
        status,
        success,
        elapsed,
    )
    return response


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _new_run_id() -> str:
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{secrets.token_hex(4)}"
