"""Tests for the deterministic verifier (no LLM involved)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.llm import schemas as llm
from app.runner.base import get_assertion
from app.runner.verifier import (
    ContainsAssertion,
    NarrationAssertion,
    PathAssertion,
    RegexAssertion,
    StatusAssertion,
    resolve_path,
    stringify,
    verify_one,
    verify_tests,
)


def _result(status=200, body=None):
    return llm.HttpResult(status_code=status, body=body)


def _case(expected, cid="TC-1", error=None, http=None):
    return llm.TestCaseResult(
        case=llm.TestCase(
            id=cid, request=llm.HttpRequest(method="GET", path="/x"), expected=expected
        ),
        http=http,
        error=error,
    )


# --------------------------------------------------------------------------
# Path resolver
# --------------------------------------------------------------------------


def test_resolve_path_nested_index():
    assert resolve_path({"items": [{"id": 5}]}, "$.items[0].id") == 5


def test_resolve_path_dotted():
    assert resolve_path({"items": [{"id": 5}]}, "items.0.id") == 5


def test_resolve_path_missing_returns_sentinel():
    from app.runner.verifier import _MISSING

    assert resolve_path({"a": 1}, "a.b") is _MISSING


def test_resolve_path_out_of_range():
    from app.runner.verifier import _MISSING

    assert resolve_path({"a": [1, 2]}, "a.5") is _MISSING


# --------------------------------------------------------------------------
# Individual assertions
# --------------------------------------------------------------------------


def test_status_assertion():
    assert StatusAssertion(200).run(_result(200)).passed
    assert not StatusAssertion(404).run(_result(200)).passed


def test_narration_assertion_pass():
    a = NarrationAssertion("access_token (string), expires_in (integer)")
    assert a.run(_result(200, {"access_token": "x", "expires_in": 3600})).passed


def test_narration_assertion_type_mismatch():
    a = NarrationAssertion("access_token (array)")
    assert not a.run(_result(200, {"access_token": "x"})).passed


def test_narration_assertion_missing_field():
    a = NarrationAssertion("nope (string)")
    assert not a.run(_result(200, {"access_token": "x"})).passed


def test_narration_assertion_skipped_when_no_pair():
    a = NarrationAssertion("tidak ada pola di sini")
    assert a.run(_result(200, {})).skipped


def test_path_assertion():
    a = PathAssertion(["$.items[0].id"])
    assert a.run(_result(200, {"items": [{"id": 1}]})).passed
    assert not a.run(_result(200, {"items": []})).passed


def test_regex_assertion():
    a = RegexAssertion(r"token-\d+")
    assert a.run(_result(200, {"x": "id token-123"})).passed
    assert not a.run(_result(200, {"x": "id token-abc"})).passed


def test_expected_result_accepts_valid_regex():
    # Regression: a missing `import re` used to crash this with NameError.
    er = llm.ExpectedResult(regex=r"^abc")
    assert er.regex == "^abc"
    assert er.has_any_check is True


def test_expected_result_rejects_invalid_regex():
    with pytest.raises(ValidationError):
        llm.ExpectedResult(regex="[invalid")


def test_expected_result_regex_end_to_end():
    case = _case(llm.ExpectedResult(regex=r"token-\d+"), http=_result(200, {"x": "id token-123"}))
    assert verify_one(case).status == "PASS"


def test_contains_assertion():
    a = ContainsAssertion(["access_token", "expires_in"])
    assert a.run(_result(200, {"access_token": "t", "expires_in": 1})).passed
    assert not a.run(_result(200, {"access_token": "t"})).passed


# --------------------------------------------------------------------------
# Aggregation / verify_one
# --------------------------------------------------------------------------


def test_verify_pass():
    v = verify_one(
        _case(
            llm.ExpectedResult(status=200, schema_narration="access_token (string)"),
            http=_result(200, {"access_token": "t"}),
        )
    )
    assert v.status == "PASS"


def test_verify_fail_on_status():
    v = verify_one(_case(llm.ExpectedResult(status=200), http=_result(500)))
    assert v.status == "FAIL"
    assert "500" in v.reason


def test_verify_fail_on_missing_field():
    v = verify_one(
        _case(
            llm.ExpectedResult(status=200, schema_narration="nope (string)"), http=_result(200, {})
        )
    )
    assert v.status == "FAIL"


def test_verify_skipped_no_check():
    v = verify_one(_case(llm.ExpectedResult(), http=_result(200)))
    assert v.status == "SKIPPED"


def test_verify_fail_on_transport_error():
    v = verify_one(_case(llm.ExpectedResult(status=200), error="conn refused"))
    assert v.status == "FAIL"
    assert "refused" in v.reason


def test_verify_skipped_no_http():
    v = verify_one(_case(llm.ExpectedResult(status=200), http=None))
    assert v.status == "SKIPPED"


def test_verify_skipped_when_case_needs_review():
    case = llm.TestCase(
        id="TC-R",
        request=llm.HttpRequest(method="GET", path="/x"),
        expected=llm.ExpectedResult(status=200),
        needs_review=True,
        review_reason="path tidak jelas",
    )
    result = llm.TestCaseResult(case=case, http=_result(200))
    v = verify_one(result)
    assert v.status == "SKIPPED"
    assert "needs_review" in v.reason
    assert "path tidak jelas" in v.reason


def test_verify_normal_when_case_does_not_need_review():
    case = llm.TestCase(
        id="TC-OK",
        request=llm.HttpRequest(method="GET", path="/x"),
        expected=llm.ExpectedResult(status=200),
        needs_review=False,
    )
    result = llm.TestCaseResult(case=case, http=_result(200))
    v = verify_one(result)
    assert v.status == "PASS"


def test_verify_error_takes_priority_over_needs_review():
    case = llm.TestCase(
        id="TC-E",
        request=llm.HttpRequest(method="GET", path="/x"),
        expected=llm.ExpectedResult(status=200),
        needs_review=True,
        review_reason="ambigu",
    )
    result = llm.TestCaseResult(case=case, http=None, error="koneksi gagal")
    v = verify_one(result)
    assert v.status == "FAIL"
    assert "koneksi gagal" in v.reason


def test_verify_tests_multiple():
    cases = [
        _case(llm.ExpectedResult(status=200), http=_result(200)),
        _case(llm.ExpectedResult(status=200), http=_result(500)),
        _case(llm.ExpectedResult(), http=_result(200)),
    ]
    verdicts = verify_tests(cases)
    assert [v.status for v in verdicts] == ["PASS", "FAIL", "SKIPPED"]


# --------------------------------------------------------------------------
# Registry + stringify
# --------------------------------------------------------------------------


def test_assertion_registry_names():
    assert get_assertion("status").__name__ == "StatusAssertion"
    assert get_assertion("narasi").__name__ == "NarrationAssertion"
    assert get_assertion("path").__name__ == "PathAssertion"
    assert get_assertion("regex").__name__ == "RegexAssertion"
    assert get_assertion("contains").__name__ == "ContainsAssertion"


def test_stringify_handles_types():
    assert stringify(None) == ""
    assert stringify({"a": 1}) == '{"a": 1}'
    assert stringify("hello") == "hello"
