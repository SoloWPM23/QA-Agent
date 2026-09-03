"""Thin orchestration nodes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.agent.state import AgentState
from app.config import load_config
from app.llm.base import LLMProvider, get_provider
from app.llm.client import LMStudioProvider
from app.llm.parsing import parse_with_retry
from app.llm.prompt_builder import build_analyze_prompt, build_explain_prompt
from app.llm.schemas import (
    AnalyzeResult,
    AuthConfig,
    ExplainResult,
    HttpRequest,
    TestCaseResult,
    Verdict,
)
from app.runner.base import VerdictBuilder
from app.runner.http_client import HttpxExecutor, apply_auth
from app.runner.reporter import persist_reports, render_reports
from app.runner.verifier import verify_tests


def parse_tests(
    state: AgentState,
    provider: LLMProvider | None = None,
) -> AgentState:
    """Translate state.chunks into a TestSuite."""
    if provider is None:
        provider = _default_provider(state.provider_config)
    suite = provider.parse_test_suite(
        state.chunks,
        base_url=state.base_url,
        auth=state.auth,
    )
    return state.model_copy(update={"test_cases": suite.cases, "suite": suite})


def _default_provider(config: dict[str, str] | None = None) -> LLMProvider:
    """Instantiate the configured provider from the registry."""
    cfg = config or {}
    base_url = cfg.get("base_url") or load_config().lm_studio_url
    model = cfg.get("model") or load_config().lm_model
    try:
        cls = get_provider("lm_studio")
    except KeyError:  # pragma: no cover - registry populated on import.
        cls = LMStudioProvider
    return cls(base_url=base_url, model=model)


def execute_tests(
    state: AgentState,
    executor: HttpxExecutor | None = None,
    auth: AuthConfig | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> AgentState:
    """Run every parsed test case deterministically and collect results."""
    ex = executor or HttpxExecutor()
    auth_cfg = auth if auth is not None else state.auth
    results: list[TestCaseResult] = []
    for case in state.test_cases:
        label = f"{case.id or '(no-id)'}: {case.title or '(no title)'}"
        if progress_callback is not None:
            progress_callback(label)
        req: HttpRequest = case.request.model_copy(deep=True)
        apply_auth(req, auth_cfg)
        try:
            http_result = ex.call(req, base_url=state.base_url)
            results.append(TestCaseResult(case=case, http=http_result))
        except Exception as exc:  # noqa: BLE001 - any failure captured, not raised.
            results.append(
                TestCaseResult(case=case, http=None, error=f"{type(exc).__name__}: {exc}")
            )
    return state.model_copy(update={"results": results})


def verify_results(state: AgentState) -> AgentState:
    """Verify every executed result deterministically into verdicts."""
    verdicts = verify_tests(state.results)
    return state.model_copy(update={"verdicts": verdicts})


def explain_results(
    state: AgentState,
    provider: LLMProvider | None = None,
) -> AgentState:
    """Ask the LLM to explain each failed verdict."""
    if provider is None:
        provider = _default_provider(state.provider_config)

    result_map = {r.case.id or "(no-id)": r for r in state.results}
    verdicts: list[Verdict] = []

    for verdict in state.verdicts:
        if verdict.status != "FAIL":
            verdicts.append(verdict)
            continue

        result = result_map.get(verdict.case_id)
        explanation = _generate_explanation(provider, verdict, result)
        verdicts.append(verdict.model_copy(update={"explanation": explanation}))

    return state.model_copy(update={"verdicts": verdicts})


def _generate_explanation(
    provider: LLMProvider,
    verdict: Verdict,
    result: TestCaseResult | None,
) -> str:
    """Generate a human-friendly explanation for a failed test case."""
    if result is None:
        return "Explanation unavailable because the test execution result is missing."

    case_dict = result.case.model_dump()
    http_dict = result.http.model_dump() if result.http else None
    assertion_details = [a.model_dump() for a in verdict.assertions]

    try:
        res = parse_with_retry(
            provider,
            build_explain_prompt(case_dict, http_dict, assertion_details),
            ExplainResult,
        )
        return res.explanation or "No explanation provided by the model."
    except Exception as exc:  # noqa: BLE001 - explanation failure is non-blocking.
        return (
            "Automatic explanation could not be generated because LM Studio "
            f"or the model encountered an issue: {type(exc).__name__}: {exc}. "
            "Please check the connection/model and try again."
        )


def render_report(
    state: AgentState,
    formats: list[str] | None = None,
) -> AgentState:
    """Build the run summary and render the requested reports."""
    if formats is None:
        formats = ["markdown", "json"]
    builder = VerdictBuilder(base_url=state.base_url)
    builder.verdicts = state.verdicts
    builder.results = state.results
    summary = builder.summarize()
    rendered = render_reports(summary, formats)
    stdout = rendered.get("markdown") or next(iter(rendered.values()))
    return state.model_copy(update={"stdout_report": stdout})


def analyze(
    state: AgentState,
    provider: LLMProvider | None = None,
) -> AgentState:
    """Run the optional LLM analyst over ambiguous or failed cases."""
    if provider is None:
        provider = _default_provider(state.provider_config)

    verdict_map = {v.case_id: v for v in state.verdicts}
    analysis: dict[str, Any] = {}

    for result in state.results:
        case = result.case
        case_id = case.id or "(no-id)"
        verdict = verdict_map.get(case_id)

        if not case.needs_review and (verdict is None or verdict.status != "FAIL"):
            continue

        note = ""
        if verdict is not None:
            note = f"verdict={verdict.status}: {verdict.reason}"

        try:
            res = parse_with_retry(
                provider,
                build_analyze_prompt(case.model_dump(), note),
                AnalyzeResult,
            )
            analysis[case_id] = res.model_dump()
        except Exception as exc:  # noqa: BLE001 - analyst failure is non-blocking.
            analysis[case_id] = {"error": f"{type(exc).__name__}: {exc}"}

    return state.model_copy(update={"analysis": analysis})


def persist_run_report(
    state: AgentState,
    report_dir: str | None = None,
) -> list[str]:
    """Persist the Excel report to disk (used by CLI)."""
    if report_dir is None:
        report_dir = load_config().report_dir

    Path(report_dir).mkdir(parents=True, exist_ok=True)

    builder = VerdictBuilder(base_url=state.base_url)
    builder.verdicts = state.verdicts
    builder.results = state.results
    summary = builder.summarize()

    format_paths = {
        "excel": str(Path(report_dir) / "report.xlsx"),
    }
    return persist_reports(summary, format_paths)


def compute_exit_code(verdicts: list[Verdict]) -> int:
    """Return the CLI exit code implied by a list of verdicts."""
    if not verdicts:
        return 2
    if any(v.status == "FAIL" for v in verdicts):
        return 1
    return 0
