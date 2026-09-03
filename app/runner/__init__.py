"""Runner layer: HTTP execution, deterministic verification, and reporting.

Importing this package triggers registration of the executor, auth, assertion,
and reporter implementations into their registries so named lookups work.
"""

from __future__ import annotations

from app.runner import base, http_client, reporter, verifier
from app.runner.http_client import HttpxExecutor, apply_auth
from app.runner.reporter import persist_reports, render_reports
from app.runner.verifier import verify_one, verify_tests

__all__ = [
    "HttpxExecutor",
    "apply_auth",
    "base",
    "http_client",
    "persist_reports",
    "render_reports",
    "reporter",
    "verifier",
    "verify_one",
    "verify_tests",
]
