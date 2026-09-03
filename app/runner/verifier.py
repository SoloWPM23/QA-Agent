"""Deterministic verifier: turn an ExpectedResult into Assertions and a Verdict."""

from __future__ import annotations

import json
import re
from typing import Any

from app.llm.schemas import (
    AssertionDetail,
    ExpectedResult,
    HttpResult,
    TestCaseResult,
    Verdict,
)
from app.runner.base import Assertion, AssertionOutcome, register_assertion

_MISSING = object()


def stringify(body: Any) -> str:
    """Render a body for substring/regex checks."""
    if body is None:
        return ""
    if isinstance(body, str):
        return body
    if isinstance(body, (dict, list, tuple)):
        return json.dumps(body, ensure_ascii=False)
    return str(body)


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


@register_assertion("status")
class StatusAssertion:
    """ExpectedResult.status must equal the response status code."""

    def __init__(self, expected_status: int) -> None:
        self.expected_status = expected_status

    def run(self, result: HttpResult) -> AssertionOutcome:
        ok = result.status_code == self.expected_status
        return AssertionOutcome(
            passed=ok,
            expected=str(self.expected_status),
            actual=str(result.status_code),
            details=f"status_code {result.status_code} == {self.expected_status}",
        )


_TYPE_CHECKS: dict[str, Any] = {
    "string": str,
    "str": str,
    "int": (int, float),
    "integer": (int, float),
    "number": (int, float),
    "float": (int, float),
    "bool": bool,
    "boolean": bool,
    "array": list,
    "list": list,
    "object": dict,
    "dict": dict,
}


@register_assertion("narasi")
class NarrationAssertion:
    """Loose check over the field (type) narration copied from the document."""

    _PAIR = re.compile(r"(\w+)\s*\((\w+)\)")

    def __init__(self, schema_narration: str) -> None:
        self.pairs = self._PAIR.findall(schema_narration or "")
        self.schema_narration = schema_narration or ""

    def run(self, result: HttpResult) -> AssertionOutcome:
        if not self.pairs:
            return AssertionOutcome(
                passed=False, skipped=True, details="no field (type) pairs extracted"
            )
        body = result.body
        if not isinstance(body, dict):
            return AssertionOutcome(
                passed=False,
                expected="JSON object",
                actual=type(body).__name__,
                details=f"response is not a JSON object ({type(body).__name__}), fields cannot be checked",
            )
        for field, type_name in self.pairs:
            if field not in body:
                return AssertionOutcome(
                    passed=False,
                    expected=f"field {field!r} present",
                    actual="missing",
                    details=f"missing field: {field!r}",
                )
            actual = body[field]
            expected_type = _TYPE_CHECKS.get(type_name.lower())
            if expected_type is not None and not isinstance(actual, expected_type):
                return AssertionOutcome(
                    passed=False,
                    expected=f"{field}: {type_name}",
                    actual=f"{field}: {type(actual).__name__}",
                    details=f"field {field!r} type: {type(actual).__name__} is not {type_name}",
                )
        return AssertionOutcome(
            passed=True,
            expected=f"{len(self.pairs)} fields match",
            actual=f"{len(self.pairs)} fields match",
            details=f"{len(self.pairs)} fields match",
        )


def resolve_path(data: Any, expression: str) -> Any:
    """Resolve a dot/[n] path expression against a JSON body."""
    tokens = _path_tokens(expression)
    current = data
    for token in tokens:
        if isinstance(current, dict) and isinstance(token, str):
            if token not in current:
                return _MISSING
            current = current[token]
        elif isinstance(current, list) and isinstance(token, int):
            if token < 0 or token >= len(current):
                return _MISSING
            current = current[token]
        elif isinstance(current, list) and isinstance(token, str):
            return _MISSING
        else:
            return _MISSING
    return current


def _path_tokens(expression: str) -> list[str | int]:
    expr = (expression or "").strip()
    expr = expr.removeprefix("$")
    expr = expr.replace("[", ".").replace("]", "")
    tokens: list[str | int] = []
    for part in expr.split("."):
        if not part:
            continue
        try:
            tokens.append(int(part))
        except ValueError:
            tokens.append(part)
    return tokens


@register_assertion("path")
class PathAssertion:
    """Each JSONPath expression must resolve to a value in the response body."""

    def __init__(self, expressions: list[str]) -> None:
        self.expressions = list(expressions)

    def run(self, result: HttpResult) -> AssertionOutcome:
        if not self.expressions:
            return AssertionOutcome(passed=False, skipped=True, details="no path expressions")
        for expr in self.expressions:
            if resolve_path(result.body, expr) is _MISSING:
                return AssertionOutcome(
                    passed=False,
                    expected=f"path {expr!r} exists",
                    actual="missing",
                    details=f"path not found: {expr!r}",
                )
        return AssertionOutcome(
            passed=True,
            expected=f"{len(self.expressions)} paths exist",
            actual=f"{len(self.expressions)} paths exist",
            details=f"{len(self.expressions)} paths found",
        )


@register_assertion("regex")
class RegexAssertion:
    """A regex must match somewhere in the stringified response body."""

    def __init__(self, pattern: str) -> None:
        self.pattern = re.compile(pattern)

    def run(self, result: HttpResult) -> AssertionOutcome:
        text = stringify(result.body)
        ok = self.pattern.search(text) is not None
        return AssertionOutcome(
            passed=ok,
            expected=f"regex {self.pattern.pattern!r} matches",
            actual="matched" if ok else "not matched",
            details=f"regex matches: {self.pattern.pattern!r}"
            if ok
            else f"regex does not match: {self.pattern.pattern!r}",
        )


@register_assertion("contains")
class ContainsAssertion:
    """Every substring must be present in the stringified response body."""

    def __init__(self, substrings: list[str]) -> None:
        self.substrings = list(substrings)

    def run(self, result: HttpResult) -> AssertionOutcome:
        text = stringify(result.body)
        missing = [s for s in self.substrings if s not in text]
        if missing:
            return AssertionOutcome(
                passed=False,
                expected=f"contains {self.substrings!r}",
                actual=f"missing {missing!r}",
                details=f"missing substrings: {missing!r}",
            )
        if not self.substrings:
            return AssertionOutcome(passed=False, skipped=True, details="no substrings")
        return AssertionOutcome(
            passed=True,
            expected=f"contains {self.substrings!r}",
            actual="all found",
            details=f"{len(self.substrings)} substrings found",
        )


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


def _build_assertions(expected: ExpectedResult) -> list[Assertion]:
    assertions: list[Assertion] = []
    if expected.status is not None:
        assertions.append(StatusAssertion(expected.status))
    if expected.schema_narration:
        assertions.append(NarrationAssertion(expected.schema_narration))
    if expected.jsonpath:
        assertions.append(PathAssertion(expected.jsonpath))
    if expected.regex:
        assertions.append(RegexAssertion(expected.regex))
    if expected.contains:
        assertions.append(ContainsAssertion(expected.contains))
    return assertions


def _outcome_to_detail(name: str, outcome: AssertionOutcome) -> AssertionDetail:
    return AssertionDetail(
        name=name,
        passed=outcome.passed,
        expected=outcome.expected,
        actual=outcome.actual,
        details=outcome.details,
    )


def verify_one(result: TestCaseResult) -> Verdict:
    """Run every assertion implied by the case's ExpectedResult -> one Verdict."""
    case_id = result.case.id or "(no-id)"
    if result.error:
        return Verdict(
            case_id=case_id,
            status="FAIL",
            reason=f"execution error: {result.error}",
            assertions=[
                AssertionDetail(
                    name="execution",
                    passed=False,
                    expected="request succeeds",
                    actual=f"error: {result.error}",
                    details=f"execution error: {result.error}",
                )
            ],
        )
    if result.http is None:
        return Verdict(case_id=case_id, status="SKIPPED", reason="no HTTP result")
    if result.case.needs_review:
        reason = result.case.review_reason or "needs review"
        return Verdict(case_id=case_id, status="SKIPPED", reason=f"needs_review: {reason}")
    if not result.case.expected.has_any_check:
        return Verdict(case_id=case_id, status="SKIPPED", reason="no checks defined")

    assertions = _build_assertions(result.case.expected)
    details: list[AssertionDetail] = []
    failures: list[str] = []
    passes = 0
    for assertion in assertions:
        outcome = assertion.run(result.http)
        details.append(_outcome_to_detail(assertion.__class__.__name__, outcome))
        if outcome.skipped:
            continue
        if not outcome.passed:
            failures.append(outcome.details)
        else:
            passes += 1

    if failures:
        return Verdict(
            case_id=case_id,
            status="FAIL",
            reason="; ".join(failures),
            assertions=details,
        )
    return Verdict(
        case_id=case_id,
        status="PASS",
        reason=f"{passes} checks passed",
        assertions=details,
    )


def verify_tests(results: list[TestCaseResult]) -> list[Verdict]:
    """Verify a list of executed test cases, returning one Verdict each."""
    return [verify_one(r) for r in results]
