"""Deterministic unit tests for the tolerant JSON parser (M0 core).

No real LLM is used; a FakeProvider stands in for the transport. These cover
extract_json (fences, comments, largest-value, empty) and parse_with_retry
(success, retry-then-success, and ParseError after exhausting attempts).
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app.llm.parsing import (
    ParseError,
    extract_json,
    parse_with_retry,
    validation_feedback,
)


class _Toy(BaseModel):
    ok: bool


# --------------------------------------------------------------------------
# extract_json
# --------------------------------------------------------------------------


def test_extract_json_plain():
    assert extract_json('{"ok": true}') == {"ok": True}


def test_extract_json_empty_raises():
    with pytest.raises(ValueError):
        extract_json("   ")


def test_extract_json_last_fence_wins():
    raw = '```json\n{"ok": false}\n```\nBerikut jawaban sebenarnya:\n```json\n{"ok": true}\n```'
    assert extract_json(raw) == {"ok": True}


def test_extract_json_with_js_comments():
    raw = '{\n  "ok": true, // Jawaban benar\n  /* blok */ "x": 1\n}'
    assert extract_json(raw)["ok"] is True


def test_extract_json_largest_balanced_value():
    # A corrupt outer object plus a small nested {} -> must pick the largest
    # valid candidate, not the tiny nested one.
    raw = '{"outer": {"valid": 1}} trailing text {ignore}'
    val = extract_json(raw)
    assert val == {"outer": {"valid": 1}}


def test_extract_json_fallback_nullish():
    with pytest.raises(ValueError):
        extract_json("tidak ada json di sini sama sekali")


# --------------------------------------------------------------------------
# validation_feedback
# --------------------------------------------------------------------------


def test_validation_feedback_mentions_field():
    with pytest.raises(ValidationError) as excinfo:
        _Toy.model_validate({"missing": True})  # 'ok' required -> ValidationError
    msg = validation_feedback(excinfo.value)
    assert "ok" in msg


# --------------------------------------------------------------------------
# parse_with_retry
# --------------------------------------------------------------------------


class _FakeProvider:
    """Emits canned responses; optionally fixes output after a failed attempt."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def chat(self, messages, temperature=0.0, json_mode=True):
        self.calls += 1
        if self._responses:
            return self._responses.pop(0)
        raise RuntimeError("no more canned responses")


def test_parse_with_retry_success_first_try():
    p = _FakeProvider(['{"ok": true}'])
    assert parse_with_retry(p, [{"role": "user", "content": "x"}], _Toy).ok is True
    assert p.calls == 1


def test_parse_with_retry_recovers_after_bad_json():
    p = _FakeProvider(["{bukan json}", '{"ok": true}'])
    assert parse_with_retry(p, [{"role": "user", "content": "x"}], _Toy).ok is True
    assert p.calls == 2


def test_parse_with_retry_raises_after_exhaustion():
    # Always invalid -> 3 attempts, then ParseError.
    p = _FakeProvider(["{bukan json}"] * 5)
    with pytest.raises(ParseError):
        parse_with_retry(p, [{"role": "user", "content": "x"}], _Toy)
    assert p.calls == 3  # MAX_RETRIES(2) + 1 initial attempt
