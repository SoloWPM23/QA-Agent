"""Tests for the report renderers (Markdown + JSON), no LLM involved."""

from __future__ import annotations

import json

from app.runner.base import get_reporter
from app.runner.reporter import (
    JsonReporter,
    MarkdownReporter,
    persist_reports,
    render_reports,
)

_SUMMARY = {
    "base_url": "http://x",
    "total": 2,
    "passed": 1,
    "failed": 1,
    "skipped": 0,
    "verdicts": [
        {"case_id": "TC-1", "status": "PASS", "reason": "2 check lolos"},
        {"case_id": "TC-2", "status": "FAIL", "reason": "status_code 500 == 200"},
    ],
}


def test_markdown_reporter_includes_counts_and_cases():
    text = MarkdownReporter().render(_SUMMARY)
    assert "**Total:** 2" in text
    assert "**PASS:** 1" in text
    assert "**FAIL:** 1" in text
    assert "| TC-1 | PASS | 2 check lolos |" in text
    assert "| TC-2 | FAIL | status_code 500 == 200 |" in text


def test_markdown_reporter_escapes_pipes_in_reason():
    summary = {**_SUMMARY, "verdicts": [{"case_id": "TC-9", "status": "FAIL", "reason": "a | b"}]}
    text = MarkdownReporter().render(summary)
    assert "a \\| b" in text


def test_json_reporter_roundtrips():
    text = JsonReporter().render(_SUMMARY)
    data = json.loads(text)
    assert data["passed"] == 1
    assert data["verdicts"][0]["case_id"] == "TC-1"


def test_render_reports_multiple_formats():
    rendered = render_reports(_SUMMARY, ["markdown", "json"])
    assert set(rendered) == {"markdown", "json"}
    assert "Total" in rendered["markdown"]
    assert "passed" in json.loads(rendered["json"])


def test_reporter_registry_names():
    assert get_reporter("markdown").__name__ == "MarkdownReporter"
    assert get_reporter("json").__name__ == "JsonReporter"


def test_persist_reports_writes_files(tmp_path):
    paths = {
        "markdown": str(tmp_path / "report.md"),
        "json": str(tmp_path / "report.json"),
    }
    written = persist_reports(_SUMMARY, paths)
    assert written == [paths["markdown"], paths["json"]]
    assert (
        (tmp_path / "report.md")
        .read_text(encoding="utf-8")
        .startswith("# Test Suite Execution Report")
    )
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["total"] == 2
