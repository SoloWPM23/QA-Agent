"""Tests for the M3 agent nodes (execute / verify / report), no LLM."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.agent import nodes
from app.agent.state import AgentState
from app.llm import schemas as llm


class _FakeExecutor:
    """Canned executor driven by a mapping of request keys to HttpResult."""

    def __init__(self):
        self.calls = []

    def call(self, req, base_url=""):
        self.calls.append((req.method, req.path, dict(req.headers)))
        if req.path == "/ok":
            return llm.HttpResult(status_code=200, body={"access_token": "t"})
        if req.path == "/boom":
            raise ConnectionError("koneksi ditolak")
        return llm.HttpResult(status_code=500, body={})


def _state(cases):
    return AgentState(base_url="http://x", test_cases=cases)


def _case(cid, method, path, status=None, narration=None):
    return llm.TestCase(
        id=cid,
        request=llm.HttpRequest(method=method, path=path),
        expected=llm.ExpectedResult(status=status, schema_narration=narration),
    )


def test_execute_tests_collects_results():
    state = _state([_case("TC-1", "GET", "/ok", status=200)])
    out = nodes.execute_tests(state, executor=_FakeExecutor())
    assert len(out.results) == 1
    assert out.results[0].http is not None
    assert out.results[0].error is None


def test_execute_tests_captures_transport_error():
    state = _state([_case("TC-2", "GET", "/boom", status=200)])
    out = nodes.execute_tests(state, executor=_FakeExecutor())
    assert out.results[0].http is None
    assert "koneksi ditolak" in out.results[0].error


def test_execute_tests_applies_bearer_auth():
    ex = _FakeExecutor()
    state = _state([_case("TC-1", "GET", "/ok", status=200)])
    state.auth = llm.AuthConfig(type="bearer", token="TK")
    nodes.execute_tests(state, executor=ex)
    assert ex.calls[0][2]["Authorization"] == "Bearer TK"
    # original parsed request is not mutated
    assert state.test_cases[0].request.headers == {}


def test_verify_results_statuses():
    state = _state([_case("TC-1", "GET", "/ok", status=200)])
    out = nodes.verify_results(nodes.execute_tests(state, executor=_FakeExecutor()))
    assert [v.status for v in out.verdicts] == ["PASS"]


def test_verify_results_fail_on_status():
    state = _state([_case("TC-9", "GET", "/absent", status=200)])
    out = nodes.verify_results(nodes.execute_tests(state, executor=_FakeExecutor()))
    assert out.verdicts[0].status == "FAIL"


def test_verify_results_transport_error_fails():
    state = _state([_case("TC-2", "GET", "/boom", status=200)])
    out = nodes.verify_results(nodes.execute_tests(state, executor=_FakeExecutor()))
    assert out.verdicts[0].status == "FAIL"


def test_render_report_produces_markdown_stdout(tmp_path):
    state = _state([_case("TC-1", "GET", "/ok", status=200)])
    s1 = nodes.execute_tests(state, executor=_FakeExecutor())
    s2 = nodes.verify_results(s1)
    s3 = nodes.render_report(s2)
    assert s3.stdout_report.startswith("# Test Suite Execution Report")
    assert "TC-1 | PASS" in s3.stdout_report


# ---------------------------------------------------------------------------
# Live end-to-end through a real in-process HTTP server
# ---------------------------------------------------------------------------


class _Echo(BaseHTTPRequestHandler):
    def _go(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        payload = json.dumps(
            {
                "method": self.command,
                "path": self.path.split("?")[0],
                "body": json.loads(body) if body else None,
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _go
    do_POST = _go

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def live_base():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Echo)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_live_execute_verify_flow(live_base):
    # Use the real httpx executor end-to-end.
    from app.runner.http_client import HttpxExecutor

    state = AgentState(
        base_url=live_base,
        test_cases=[
            _case("TC-LIVE", "POST", "/items", status=200),
        ],
    )
    out = nodes.execute_tests(state, executor=HttpxExecutor())
    assert out.results[0].http.status_code == 200
    assert out.results[0].http.body["method"] == "POST"
    v = nodes.verify_results(out)
    assert v.verdicts[0].status == "PASS"
