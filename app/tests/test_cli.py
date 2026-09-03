"""Tests for the CLI runner (M5).

The real LLM and HTTP layers are monkey-patched so the CLI can be exercised
offline and deterministically.
"""

from __future__ import annotations

from app import cli
from app.llm.schemas import Verdict


def _patch_pipeline(monkeypatch, verdicts):
    monkeypatch.setattr(cli, "load_document", lambda path: [])

    def fake_run(state, **kwargs):
        return state.model_copy(update={"verdicts": verdicts})

    monkeypatch.setattr(cli.graph, "run", fake_run)
    monkeypatch.setattr(
        cli,
        "persist_run_report",
        lambda state, report_dir: [f"{report_dir}/report.md", f"{report_dir}/report.json"],
    )


def test_cli_all_pass(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch, [Verdict(case_id="TC-1", status="PASS")])
    code = cli.main(
        [
            "--suite",
            "suite.md",
            "--base-url",
            "http://x",
            "--output",
            str(tmp_path),
        ]
    )
    assert code == 0


def test_cli_has_fail(monkeypatch, tmp_path):
    _patch_pipeline(
        monkeypatch,
        [
            Verdict(case_id="TC-1", status="PASS"),
            Verdict(case_id="TC-2", status="FAIL", reason="status 500"),
        ],
    )
    code = cli.main(
        [
            "--suite",
            "suite.md",
            "--base-url",
            "http://x",
            "--output",
            str(tmp_path),
        ]
    )
    assert code == 1


def test_cli_empty_verdicts(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch, [])
    code = cli.main(
        [
            "--suite",
            "suite.md",
            "--base-url",
            "http://x",
            "--output",
            str(tmp_path),
        ]
    )
    assert code == 2


def test_cli_with_basic_auth(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch, [Verdict(case_id="TC-1", status="PASS")])
    code = cli.main(
        [
            "--suite",
            "suite.md",
            "--base-url",
            "http://x",
            "--auth-type",
            "basic",
            "--username",
            "u",
            "--password",
            "p",
            "--output",
            str(tmp_path),
        ]
    )
    assert code == 0


def test_cli_analyze_flag(monkeypatch, tmp_path):
    calls = []

    def fake_run(state, analyze=False, **kwargs):
        calls.append(analyze)
        return state.model_copy(update={"verdicts": [Verdict(case_id="TC-1", status="PASS")]})

    monkeypatch.setattr(cli, "load_document", lambda path: [])
    monkeypatch.setattr(cli.graph, "run", fake_run)
    monkeypatch.setattr(
        cli,
        "persist_run_report",
        lambda state, report_dir: [f"{report_dir}/report.md", f"{report_dir}/report.json"],
    )

    cli.main(
        [
            "--suite",
            "suite.md",
            "--base-url",
            "http://x",
            "--analyze",
            "--output",
            str(tmp_path),
        ]
    )
    assert calls == [True]
