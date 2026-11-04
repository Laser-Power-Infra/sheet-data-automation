from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    dry_run: bool | None = None
    date_override: dt.date | None = None


class JobRunResult(BaseModel):
    name: str
    success: bool
    exit_code: int
    failures: list[str] = Field(default_factory=list)
    duration_seconds: float


class RunResponse(BaseModel):
    success: bool
    status: str
    run_id: str
    started_at: str
    duration_seconds: float
    jobs: list[JobRunResult]
    error: str | None = None
