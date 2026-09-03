"""LIVE behavior tests (determinism + recovery) against the real model (M0).

Auto-skipped when LM Studio is offline (see app/tests/live.py). Verifies the
repeatability and non-blocking recovery behaviors that the deterministic
parsing layer guarantees.
"""

from __future__ import annotations

from app.llm import schemas as llm
from app.llm.client import LMStudioProvider
from app.llm.parsing import parse_with_retry
from app.llm.prompt_builder import build_case_prompt
from app.tests.live import requires_lm_studio


def _tc(table: str) -> llm.TestCase:
    return parse_with_retry(LMStudioProvider(), build_case_prompt(table), llm.TestCase)


@requires_lm_studio()
def test_determinism_repeated() -> None:
    table = """[Test Case TC-010]
ID: TC-010
Judul: Get users
Metode: GET
Path: /api/v1/users
Expected Status Code: 200
Expected Schema: harus memuat users (array)"""
    results = [_tc(table) for _ in range(3)]
    parsed = [r for r in results if r is not None]
    assert len(parsed) == 3  # all attempts succeeded
    assert all(r.id == "TC-010" for r in parsed)
    assert all(r.request.method == "GET" for r in parsed)
    assert all(r.request.path == "/api/v1/users" for r in parsed)
    assert all(r.expected.status == 200 for r in parsed)


@requires_lm_studio()
def test_missing_path_becomes_needs_review() -> None:
    table = """[Test Case TC-020]
ID: TC-020
Judul: Cek endpoint tanpa path
Metode: GET
Expected Status Code: 200"""
    tc = _tc(table)
    assert tc.needs_review is True
    assert tc.request.path in ("", "/", None)


@requires_lm_studio()
def test_invalid_method_recovers_to_valid() -> None:
    """ "TRACE" (invalid) must recover to a valid HTTP method, flagged for review."""
    table = """[Test Case TC-030]
ID: TC-030
Judul: Uji retry
Metode: TRACE
Path: /x
Expected Status Code: 200"""
    tc = _tc(table)
    # Recovery target is LLM-determined; what matters is a valid enum value.
    assert tc.request.method in ("GET", "POST", "PUT", "PATCH", "DELETE")
    assert tc.needs_review is True


@requires_lm_studio()
def test_body_array_allowed() -> None:
    table = """[Test Case TC-040]
ID: TC-040
Judul: Post list
Metode: POST
Path: /api/v1/batch
Body (JSON): [{"id": 1}, {"id": 2}]
Expected Status Code: 201"""
    tc = _tc(table)
    assert tc.request.method == "POST"
    assert tc.request.path == "/api/v1/batch"
    assert tc.expected.status == 201
    assert isinstance(tc.request.body, list)
