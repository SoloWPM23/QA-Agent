"""Agent layer: thin orchestration nodes and a simple pipeline run.

The pipeline is a plain sequence of nodes (parse -> execute -> verify ->
report) rather than a heavyweight graph framework for the MVP. graph.run()
returns the final AgentState so the caller can inspect results, verdicts, and
the rendered stdout report (PLAN 6.9).
"""

from __future__ import annotations

from app.agent import nodes
from app.agent.nodes import execute_tests, parse_tests, render_report, verify_results
from app.agent.state import AgentState

__all__ = [
    "AgentState",
    "execute_tests",
    "nodes",
    "parse_tests",
    "render_report",
    "verify_results",
]
