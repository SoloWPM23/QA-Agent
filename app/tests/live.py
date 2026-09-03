"""Shared helpers for LIVE (real LLM) integration tests.

Live tests hit the real LM Studio server, so they are auto-skipped when the
server is not reachable. This keeps CI / offline `pytest app/tests/` fast and
deterministic (PLAN M6) while still allowing an explicit run against a live
model.
"""

from __future__ import annotations

import os
import socket
from functools import lru_cache

import pytest

from app.config import load_config

_DEFAULT_HOST = "localhost"
_TIMEOUT_S = 1.0


@lru_cache(maxsize=1)
def _lm_studio_reachable() -> bool:
    """Probe the LM Studio server with a lightweight TCP connect (no HTTP).

    Cached per-process so repeated live-test markers do not re-read config or
    re-open a socket for every decorated function.
    """
    cfg = load_config()
    url = cfg.lm_studio_url or os.getenv("LM_STUDIO_URL", "")
    # Normalize "scheme://host:port/path" -> (host, port).
    cleaned = url.split("://")[-1].split("/")[0]
    host, _, port = cleaned.rpartition(":")
    try:
        port = int(port) if port else 80
    except ValueError:
        port = 80
    host = host or _DEFAULT_HOST
    try:
        with socket.create_connection((host, port), timeout=_TIMEOUT_S):
            return True
    except OSError:
        return False


def requires_lm_studio():
    """Skip the decorated test when the live LM Studio server is unavailable.

    Usage:
        @requires_lm_studio()
        def test_something_live():
            ...
    """
    return pytest.mark.skipif(
        not _lm_studio_reachable(),
        reason="LM Studio lokal tidak aktif; lewati test live.",
    )
