"""Pydantic contracts shared across the pipeline.

These models are the single contract between the LLM layer (output),
the executor (HTTP requests), the verifier (assertions), and the reporter.
Fields with defaults follow the backward-compatible discipline (PLAN 12.3).

Models that receive LLM output directly (HttpRequest, ExpectedResult,
TestCase, TestSuite) forbid extra fields so hallucinated keys fail fast at
validation time instead of silently disappearing.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HttpRequest(BaseModel):
    """A concrete HTTP request produced by the LLM from the test suite doc."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    # Query values are strings in real HTTP; list[str] covers repeated params.
    query: dict[str, str | list[str]] = Field(default_factory=dict)
    body: Any = None  # JSON body: object, array, or primitive are all legal.

    @field_validator("path")
    @classmethod
    def _path_must_lead_with_slash(cls, value: str) -> str:
        """Reject relative paths unless empty (unset is handled as needs_review)."""
        if value and not value.startswith("/"):
            raise ValueError("path harus diawali '/' (contoh: /api/v1/resource)")
        return value


class ExpectedResult(BaseModel):
    """Expected checks for one test case.

    schema_narration holds the raw "field (type)" text copied verbatim
    from the document; the verifier runs a deterministic loose check on it.
    """

    model_config = ConfigDict(extra="forbid")

    status: int | None = None
    schema_narration: str | None = None
    jsonpath: list[str] = Field(default_factory=list)
    regex: str | None = None
    contains: list[str] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def _status_must_be_http_range(cls, value: int | None) -> int | None:
        """Limit status to a valid HTTP range so nonsense values fail early."""
        if value is not None and not (100 <= value <= 599):
            raise ValueError(f"status harus di rentang 100-599, bukan {value}")
        return value

    @field_validator("regex")
    @classmethod
    def _regex_must_compile(cls, value: str | None) -> str | None:
        """Compile the regex now so an invalid pattern fails at parse time."""
        if value:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"regex tidak valid: {value!r} ({exc})") from exc
        return value

    @property
    def has_any_check(self) -> bool:
        """True if any assertion field is set."""
        return any(
            (
                self.status is not None,
                self.schema_narration,
                self.jsonpath,
                self.regex,
                self.contains,
            )
        )


class TestCase(BaseModel):
    """One parsed test case, ready to be executed and verified."""

    model_config = ConfigDict(extra="forbid")

    id: str = ""
    title: str = ""
    summary: str | None = None
    request: HttpRequest = Field(default_factory=HttpRequest)
    expected: ExpectedResult = Field(default_factory=ExpectedResult)
    needs_review: bool = False
    review_reason: str | None = None


class AuthConfig(BaseModel):
    """Pure auth data from the user (basic / bearer / api_key / none)."""

    type: Literal["none", "basic", "bearer", "api_key"] = "none"
    username: str | None = None
    password: str | None = None
    token: str | None = None
    header_name: str | None = None
    header_value: str | None = None


class TestSuite(BaseModel):
    """A parsed test suite document. base_url and auth come from the user, not the LLM."""

    model_config = ConfigDict(extra="forbid")

    base_url: str = ""
    auth: AuthConfig | None = None
    cases: list[TestCase] = Field(default_factory=list)


class HttpResult(BaseModel):
    """Result of one executed HTTP request."""

    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None


class TestCaseResult(BaseModel):
    """One test case together with its HTTP execution result."""

    case: TestCase
    http: HttpResult | None = None
    error: str | None = None


class AssertionDetail(BaseModel):
    """Structured detail for a single assertion check."""

    name: str = ""
    passed: bool = False
    expected: str = ""
    actual: str = ""
    details: str = ""


class Verdict(BaseModel):
    """Final deterministic verdict for one test case."""

    case_id: str
    status: Literal["PASS", "FAIL", "SKIPPED"]
    reason: str = ""
    explanation: str | None = None
    assertions: list[AssertionDetail] = Field(default_factory=list)

    @classmethod
    def skipped(cls, case_id: str, reason: str) -> Verdict:
        """Shortcut for building a SKIPPED verdict."""
        return cls(case_id=case_id, status="SKIPPED", reason=reason)


class AnalyzeResult(BaseModel):
    """Optional LLM-as-analyst output for ambiguous or failed cases."""

    needs_review: bool | None = None
    review_reason: str | None = None


class ExplainResult(BaseModel):
    """LLM explanation for a failed test case."""

    explanation: str = ""
