"""Tests for the thin M2 agent nodes."""

from __future__ import annotations

from app.agent import nodes
from app.agent.nodes import parse_tests
from app.agent.state import AgentState
from app.core.schemas import TableBlock
from app.input.schemas import TableBlockChunk
from app.llm import schemas as llm
from app.llm.schemas import Verdict


class FakeProvider:
    """A minimal LLM-provider stand-in for unit tests (no network)."""

    captured = None

    def parse_test_suite(self, chunks, base_url=None, auth=None):
        FakeProvider.captured = (chunks, base_url, auth)
        if not chunks:
            return llm.TestSuite(base_url=base_url or "", auth=auth, cases=[])
        return llm.TestSuite(
            base_url=base_url or "",
            auth=auth,
            cases=[
                llm.TestCase(
                    id="TC-001",
                    request=llm.HttpRequest(method="GET", path="/x"),
                )
            ],
        )


def test_parse_tests_delegates_and_writes_back():
    block = TableBlock(test_case_label="Test Case TC-001", fields={"ID": "TC-001"})
    state = AgentState(
        base_url="http://target.test",
        chunks=[TableBlockChunk(block=block)],
    )

    provider = FakeProvider()
    result = parse_tests(state, provider=provider)

    # Delegates to provider with the right args.
    chunks, base_url, _ = FakeProvider.captured
    assert base_url == "http://target.test"
    assert len(chunks) == 1

    # Writes back into state (new object returned, original unchanged).
    assert result.test_cases[0].id == "TC-001"
    assert result.suite is not None
    assert result.suite.cases[0].request.method == "GET"
    # Original state untouched (immutability of the copy).
    assert state.test_cases == []


def test_parse_tests_empty_chunks():
    state = AgentState(base_url="http://target.test")
    provider = FakeProvider()
    result = parse_tests(state, provider=provider)
    assert result.test_cases == []
    assert result.suite is not None
    assert result.suite.cases == []


class FakeChatProvider:
    """A minimal LLM provider for tests that only need chat(), not parse."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict], temperature: float = 0.0, json_mode: bool = True) -> str:
        self.calls.append(messages)
        return self.content

    def supports_structured_output(self) -> bool:
        return False


def test_analyze_node_calls_llm_for_needs_review_case():
    case = llm.TestCase(
        id="TC-001",
        request=llm.HttpRequest(method="GET", path="/x"),
        expected=llm.ExpectedResult(),
        needs_review=True,
        review_reason="path tidak jelas",
    )
    state = AgentState(
        results=[llm.TestCaseResult(case=case)],
        verdicts=[
            Verdict(case_id="TC-001", status="SKIPPED", reason="needs_review: path tidak jelas")
        ],
    )
    provider = FakeChatProvider('{"needs_review": true, "review_reason": "path ambigu"}')
    out = nodes.analyze(state, provider=provider)
    assert out.analysis["TC-001"]["needs_review"] is True
    assert out.analysis["TC-001"]["review_reason"] == "path ambigu"


def test_analyze_node_calls_llm_for_failed_case():
    case = llm.TestCase(
        id="TC-002",
        request=llm.HttpRequest(method="GET", path="/y"),
        expected=llm.ExpectedResult(status=200),
    )
    state = AgentState(
        results=[llm.TestCaseResult(case=case)],
        verdicts=[Verdict(case_id="TC-002", status="FAIL", reason="status_code 500 == 200")],
    )
    provider = FakeChatProvider('{"needs_review": false, "review_reason": null}')
    out = nodes.analyze(state, provider=provider)
    assert out.analysis["TC-002"]["needs_review"] is False


def test_analyze_node_skips_passing_case():
    case = llm.TestCase(
        id="TC-003",
        request=llm.HttpRequest(method="GET", path="/z"),
        expected=llm.ExpectedResult(status=200),
    )
    state = AgentState(
        results=[llm.TestCaseResult(case=case, http=llm.HttpResult(status_code=200))],
        verdicts=[Verdict(case_id="TC-003", status="PASS", reason="1 check lolos")],
    )
    provider = FakeChatProvider('{"invalid": "should not be called"}')
    out = nodes.analyze(state, provider=provider)
    assert out.analysis == {}
    assert not provider.calls


def test_analyze_node_captures_llm_error_without_crashing():
    case = llm.TestCase(
        id="TC-004",
        request=llm.HttpRequest(method="GET", path="/w"),
        expected=llm.ExpectedResult(),
        needs_review=True,
    )
    state = AgentState(
        results=[llm.TestCaseResult(case=case)],
        verdicts=[Verdict(case_id="TC-004", status="SKIPPED", reason="needs_review")],
    )
    provider = FakeChatProvider('{"unclosed": ')  # invalid JSON
    out = nodes.analyze(state, provider=provider)
    assert "error" in out.analysis["TC-004"]


def test_explain_results_node_adds_explanation_for_failed_case():
    case = llm.TestCase(
        id="TC-005",
        title="Get user",
        request=llm.HttpRequest(method="GET", path="/users/1"),
        expected=llm.ExpectedResult(status=200),
    )
    state = AgentState(
        results=[
            llm.TestCaseResult(
                case=case, http=llm.HttpResult(status_code=500, body={"error": "boom"})
            )
        ],
        verdicts=[Verdict(case_id="TC-005", status="FAIL", reason="status_code 500 == 200")],
    )
    provider = FakeChatProvider('{"explanation": "Server returned 500 instead of 200."}')
    out = nodes.explain_results(state, provider=provider)
    assert out.verdicts[0].explanation == "Server returned 500 instead of 200."


def test_explain_results_node_skips_passing_case():
    case = llm.TestCase(
        id="TC-006",
        request=llm.HttpRequest(method="GET", path="/users"),
        expected=llm.ExpectedResult(status=200),
    )
    state = AgentState(
        results=[llm.TestCaseResult(case=case, http=llm.HttpResult(status_code=200))],
        verdicts=[Verdict(case_id="TC-006", status="PASS", reason="1 check passed")],
    )
    provider = FakeChatProvider('{"explanation": "should not be used"}')
    out = nodes.explain_results(state, provider=provider)
    assert not provider.calls
    assert out.verdicts[0].explanation is None


def test_explain_results_node_captures_llm_error_without_crashing():
    case = llm.TestCase(
        id="TC-007",
        request=llm.HttpRequest(method="GET", path="/users/1"),
        expected=llm.ExpectedResult(status=200),
    )
    state = AgentState(
        results=[llm.TestCaseResult(case=case, http=llm.HttpResult(status_code=500))],
        verdicts=[Verdict(case_id="TC-007", status="FAIL", reason="status_code 500 == 200")],
    )
    provider = FakeChatProvider('{"unclosed": ')
    out = nodes.explain_results(state, provider=provider)
    assert "LM Studio" in (out.verdicts[0].explanation or "")


def test_persist_run_report_writes_excel_file(tmp_path):
    state = AgentState(
        base_url="http://x",
        verdicts=[
            Verdict(case_id="TC-1", status="PASS", reason="ok"),
            Verdict(case_id="TC-2", status="FAIL", reason="status 500"),
        ],
    )
    written = nodes.persist_run_report(state, report_dir=str(tmp_path))
    assert len(written) == 1
    assert (tmp_path / "report.xlsx").exists()
    assert (tmp_path / "report.xlsx").stat().st_size > 0


def test_compute_exit_code_passes_and_fails():
    assert nodes.compute_exit_code([Verdict(case_id="A", status="PASS")]) == 0
    assert nodes.compute_exit_code([Verdict(case_id="A", status="SKIPPED")]) == 0
    assert nodes.compute_exit_code([Verdict(case_id="A", status="FAIL")]) == 1
    assert nodes.compute_exit_code([]) == 2
    assert (
        nodes.compute_exit_code(
            [
                Verdict(case_id="A", status="PASS"),
                Verdict(case_id="B", status="FAIL"),
            ]
        )
        == 1
    )
