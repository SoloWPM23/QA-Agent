"""In-memory job store for the web API (M5).

The MVP implementation keeps jobs in a thread-safe in-memory dict. A
production deployment can swap this for a persistent store (Redis, SQLite,
etc.) without changing the route code because the route layer only uses the
``JobStore`` interface.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class Job(BaseModel):
    """Snapshot of an async test-suite run."""

    job_id: str
    status: str  # queued | running | done | failed
    current_case: str | None = None
    error: str | None = None
    summary: dict[str, Any] | None = None
    report_paths: dict[str, str] | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class JobStore:
    """Thread-safe in-memory store for pipeline jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self) -> str:
        """Create a new queued job and return its id."""
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = Job(job_id=job_id, status="queued")
        return job_id

    def get(self, job_id: str) -> Job:
        """Return the job or raise ``KeyError`` if it does not exist."""
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return self._jobs[job_id]

    def update(self, job_id: str, **fields: Any) -> None:
        """Update job fields in place."""
        with self._lock:
            job = self._jobs[job_id]
            for key, value in fields.items():
                setattr(job, key, value)

    def list(self) -> list[Job]:
        """Return all jobs, oldest first."""
        with self._lock:
            return list(self._jobs.values())


# Global singleton used by the web routes in this MVP.
JOBS = JobStore()
