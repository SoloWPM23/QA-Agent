"""Runner-layer contracts (HTTP executor, auth, assertion, reporter) + registries.

Each concrete implementation registers itself in the matching registry so the
orchestration layer (agent nodes) can resolve it by name without knowing the
implementation details. Adding a new executor, auth scheme, assertion kind, or
report format later means adding one implementation + registering it -- the
callers and the rest of the pipeline stay unchanged (PLAN 6.6-6.8, 12.1).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.llm.schemas import AuthConfig, HttpRequest, HttpResult


class HttpExecutor(Protocol):
    """Runs one HTTP request and returns the raw result (deterministic)."""

    def call(self, req: HttpRequest) -> HttpResult:
        """Execute req and return HttpResult. Raise on hard transport failure."""
        ...


class AuthHandler(Protocol):
    """Applies a configured auth scheme onto a request before it is sent."""

    def apply(self, req: HttpRequest, cfg: AuthConfig) -> None:
        """Mutate req.headers/query so the request is authenticated."""
        ...


@dataclass
class AssertionOutcome:
    """Result of a single assertion check."""

    passed: bool
    skipped: bool = False
    details: str = ""
    expected: str = ""
    actual: str = ""

    @property
    def label(self) -> str:
        return "PASS" if self.passed else ("SKIP" if self.skipped else "FAIL")


class Assertion(Protocol):
    """A single composable, deterministic check over a HTTP result."""

    def run(self, result: HttpResult) -> AssertionOutcome: ...


class Reporter(Protocol):
    """Renders a run summary into a string or binary output."""

    def render(self, summary: dict) -> Any: ...


# ---------------------------------------------------------------------------
# Registries (normalized keys -> implementation class)
# ---------------------------------------------------------------------------

HTTP_EXECUTORS: dict[str, type[HttpExecutor]] = {}
AUTH_HANDLERS: dict[str, type[AuthHandler]] = {}
ASSERTIONS: dict[str, type[Assertion]] = {}
REPORTERS: dict[str, type[Reporter]] = {}


def _normalize(name: str) -> str:
    return name.strip().lower()


def _add(registry: dict, key: str, cls: type) -> None:
    k = _normalize(key)
    if k in registry:
        raise ValueError(f"Sudah terdaftar di registry: {k!r}")
    registry[k] = cls


def register_http_executor(name: str) -> Callable[[type], type]:
    def deco(cls: type) -> type:
        _add(HTTP_EXECUTORS, name, cls)
        return cls

    return deco


def register_auth_handler(name: str) -> Callable[[type], type]:
    def deco(cls: type) -> type:
        _add(AUTH_HANDLERS, name, cls)
        return cls

    return deco


def register_assertion(name: str) -> Callable[[type], type]:
    def deco(cls: type) -> type:
        _add(ASSERTIONS, name, cls)
        return cls

    return deco


def register_reporter(name: str) -> Callable[[type], type]:
    def deco(cls: type) -> type:
        _add(REPORTERS, name, cls)
        return cls

    return deco


def get_executor(name: str) -> type[HttpExecutor]:
    k = _normalize(name)
    if k not in HTTP_EXECUTORS:
        raise KeyError(f"Executor tidak dikenal: {name!r}. Terdaftar: {sorted(HTTP_EXECUTORS)}")
    return HTTP_EXECUTORS[k]


def get_auth_handler(name: str) -> type[AuthHandler]:
    k = _normalize(name)
    if k not in AUTH_HANDLERS:
        raise KeyError(f"Auth handler tidak dikenal: {name!r}. Terdaftar: {sorted(AUTH_HANDLERS)}")
    return AUTH_HANDLERS[k]


def get_assertion(name: str) -> type[Assertion]:
    k = _normalize(name)
    if k not in ASSERTIONS:
        raise KeyError(f"Assertion tidak dikenal: {name!r}. Terdaftar: {sorted(ASSERTIONS)}")
    return ASSERTIONS[k]


def get_reporter(name: str) -> type[Reporter]:
    k = _normalize(name)
    if k not in REPORTERS:
        raise KeyError(f"Reporter tidak dikenal: {name!r}. Terdaftar: {sorted(REPORTERS)}")
    return REPORTERS[k]


@dataclass
class VerdictBuilder:
    """Shared helper for building the summary dict handed to reporters."""

    base_url: str = ""
    cases: list = field(default_factory=list)
    verdicts: list = field(default_factory=list)
    results: list = field(default_factory=list)

    def summarize(self) -> dict:
        total = len(self.verdicts)
        passed = sum(1 for v in self.verdicts if v.status == "PASS")
        failed = sum(1 for v in self.verdicts if v.status == "FAIL")
        skipped = sum(1 for v in self.verdicts if v.status == "SKIPPED")
        result_map = {r.case.id or "(no-id)": r for r in self.results}
        verdicts_with_detail: list[dict] = []
        for v in self.verdicts:
            verdict_dict = v.model_dump()
            case_id = getattr(v, "case_id", "(no-id)")
            result = result_map.get(case_id)
            verdict_dict["detail"] = _build_case_detail(result)
            verdicts_with_detail.append(verdict_dict)
        return {
            "base_url": self.base_url,
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "verdicts": verdicts_with_detail,
        }


def _build_case_detail(result: Any) -> dict:
    """Extract request/response details from a TestCaseResult for reporting."""
    if result is None:
        return {}
    case = result.case
    http = result.http
    return {
        "title": case.title,
        "method": case.request.method,
        "path": case.request.path,
        "request_body": case.request.body,
        "response_status": http.status_code if http else None,
        "response_body": http.body if http else None,
    }
