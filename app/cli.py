"""Command-line runner for the AI QA Agent pipeline (M5).

Example:

    python -m app.cli --suite docs/test_suite.docx \\
        --base-url http://localhost:8000 \\
        --auth-type bearer --token secret123

Exit code:
- 0 if all evaluated cases passed (SKIPPED allowed).
- 1 if any case failed.
- 2 if no verdicts were produced.
"""

from __future__ import annotations

import argparse
import sys

from app.agent import graph
from app.agent.nodes import compute_exit_code, persist_run_report
from app.agent.state import AgentState
from app.config import load_config
from app.input.adapter import load_document
from app.llm.schemas import AuthConfig


def _build_auth(args: argparse.Namespace) -> AuthConfig:
    auth_type = (args.auth_type or "none").lower()
    if auth_type == "basic":
        return AuthConfig(type="basic", username=args.username, password=args.password)
    if auth_type == "bearer":
        return AuthConfig(type="bearer", token=args.token)
    if auth_type == "api_key":
        return AuthConfig(
            type="api_key",
            header_name=args.api_key_header,
            header_value=args.api_key_value,
        )
    return AuthConfig(type="none")


def main(argv: list[str] | None = None) -> int:
    """Run the full pipeline from the command line and return an exit code."""
    parser = argparse.ArgumentParser(
        prog="AI QA Agent",
        description="Jalankan test suite dokumen terhadap REST endpoint.",
    )
    parser.add_argument("--suite", required=True, help="Path dokumen test suite")
    parser.add_argument("--base-url", required=True, help="Base URL target API")
    parser.add_argument(
        "--auth-type",
        choices=["none", "basic", "bearer", "api_key"],
        default="none",
        help="Tipe autentikasi",
    )
    parser.add_argument("--username", default=None, help="Username untuk basic auth")
    parser.add_argument("--password", default=None, help="Password untuk basic auth")
    parser.add_argument("--token", default=None, help="Token untuk bearer auth")
    parser.add_argument("--api-key-header", default=None, help="Nama header untuk api_key auth")
    parser.add_argument("--api-key-value", default=None, help="Nilai header untuk api_key auth")
    parser.add_argument("--output", default="reports", help="Direktori output laporan")
    parser.add_argument(
        "--exit-on-fail",
        action="store_true",
        help="Keluar dengan kode non-zero jika ada FAIL (sama dengan perilaku default)",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Jalankan analis LLM untuk kasus ambigu/gagal",
    )

    args = parser.parse_args(argv)

    config = load_config()
    config.report_dir = args.output
    config.ensure_dirs()

    auth = _build_auth(args)
    chunks = load_document(args.suite)
    state = AgentState(
        base_url=args.base_url,
        auth=auth,
        chunks=chunks,
    )

    final_state = graph.run(state, analyze=args.analyze)
    report_paths = persist_run_report(final_state, report_dir=args.output)

    summary = {
        "base_url": final_state.base_url,
        "total": len(final_state.verdicts),
        "passed": sum(1 for v in final_state.verdicts if v.status == "PASS"),
        "failed": sum(1 for v in final_state.verdicts if v.status == "FAIL"),
        "skipped": sum(1 for v in final_state.verdicts if v.status == "SKIPPED"),
    }

    print(f"Base URL: {summary['base_url']}")
    print(
        f"Total: {summary['total']} | "
        f"PASS: {summary['passed']} | "
        f"FAIL: {summary['failed']} | "
        f"SKIPPED: {summary['skipped']}"
    )
    print(f"Report saved to: {', '.join(report_paths)}")

    return compute_exit_code(final_state.verdicts)


if __name__ == "__main__":
    sys.exit(main())
