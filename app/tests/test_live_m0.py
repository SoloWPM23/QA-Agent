"""LIVE integration tests for the raw LLM client (M0).

These hit the real LM Studio server and are auto-skipped when it is offline,
so `pytest app/tests/` stays fast and deterministic for CI while still
verifying real-model behavior on demand.
"""

from __future__ import annotations

from app.llm import schemas as llm
from app.llm.client import LMStudioProvider
from app.llm.parsing import parse_with_retry
from app.llm.prompt_builder import build_case_prompt
from app.tests.live import requires_lm_studio


@requires_lm_studio()
def test_raw_chat_returns_json() -> None:
    p = LMStudioProvider()
    out = p.chat([{"role": "user", "content": 'Balas dengan JSON: {"ok": "true"}'}])
    assert '"ok"' in out


@requires_lm_studio()
def test_full_pipeline_parses_tc001() -> None:
    p = LMStudioProvider()
    table = """[Test Case TC-001]
ID: TC-001
Judul: Ambil Profil Pengguna
Metode: GET
Path: /api/v1/users/me
Headers:
Authorization: Bearer abc123
Expected Status Code: 200
Expected Schema: Response harus memuat field: id (number), name (string)"""

    tc = parse_with_retry(p, build_case_prompt(table), llm.TestCase)
    assert tc.id == "TC-001"
    assert tc.request.method == "GET"
    assert tc.request.path == "/api/v1/users/me"
    assert tc.expected.status == 200
    # Narasi schema disalin verbatim, bukan dikonversi.
    assert "id" in tc.expected.schema_narration
    assert tc.needs_review is False
