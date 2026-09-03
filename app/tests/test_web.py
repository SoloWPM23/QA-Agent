"""Tests for the FastAPI web layer.

All expensive / non-deterministic dependencies are monkey-patched so these
 tests run offline and fast.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.agent.state import AgentState
from app.llm.schemas import HttpRequest, HttpResult, TestCase, TestCaseResult, Verdict
from app.main import create_app
from app.web import jobs as jobs_module
from app.web import routes as routes_module


@pytest.fixture
def client():
    """Provide a TestClient with isolated job store and patched services."""
    routes_module.JOBS = jobs_module.JobStore()

    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _patch_pipeline(monkeypatch):
    """Replace the real pipeline with fast, deterministic stubs."""
    fail_case = TestCase(
        id="TC-2",
        title="Fail case",
        request=HttpRequest(method="GET", path="/x"),
    )

    def fake_load_document(path: str):
        return []

    def fake_run(state: AgentState, **kwargs):
        return state.model_copy(
            update={
                "results": [
                    TestCaseResult(case=fail_case, http=HttpResult(status_code=500, body={})),
                ],
                "verdicts": [
                    Verdict(case_id="TC-1", status="PASS", reason="ok"),
                    Verdict(case_id="TC-2", status="FAIL", reason="status 500"),
                ],
            }
        )

    monkeypatch.setattr(routes_module, "load_document", fake_load_document)
    monkeypatch.setattr(routes_module.graph, "run", fake_run)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "AI QA Agent" in resp.text


def test_run_job_lifecycle(client):
    resp = client.post(
        "/api/run",
        data={
            "base_url": "http://target.test",
            "auth_type": "none",
            "lm_studio_url": "http://localhost:1234/v1",
            "lm_model": "model",
        },
        files={"file": ("suite.md", "Test Case TC-001", "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "job_id" in body
    job_id = body["job_id"]

    for _ in range(20):
        resp = client.get(f"/api/result/{job_id}")
        assert resp.status_code == 200
        payload = resp.json()
        if payload["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    else:
        pytest.fail("Job did not finish within test timeout")

    assert payload["status"] == "done"
    assert payload["summary"]["total"] == 2
    assert payload["summary"]["failed"] == 1


def test_result_unknown_job_returns_404(client):
    resp = client.get("/api/result/tidak-ada")
    assert resp.status_code == 404


def test_report_xlsx_requires_done_job(client):
    resp = client.post(
        "/api/run",
        data={"base_url": "http://target.test", "auth_type": "none"},
        files={"file": ("suite.md", "Test Case TC-001", "text/plain")},
    )
    job_id = resp.json()["job_id"]

    for _ in range(20):
        result = client.get(f"/api/result/{job_id}").json()
        if result["status"] in ("done", "failed"):
            break
        time.sleep(0.1)

    resp = client.get(f"/api/reports/{job_id}.xlsx")
    assert resp.status_code == 200
    assert "spreadsheetml.sheet" in resp.headers.get("content-type", "")


def test_auth_validation_rejects_incomplete_basic(client):
    resp = client.post(
        "/api/run",
        data={"base_url": "http://target.test", "auth_type": "basic", "username": "u"},
        files={"file": ("suite.md", "Test Case TC-001", "text/plain")},
    )
    assert resp.status_code == 422
    assert "password" in resp.text.lower()
