"""Simple deterministic pipeline: parse -> execute -> verify -> report.

Kept as a plain function (not langgraph) for the MVP; re-sequencing into a
graph later only requires calling the same thin nodes in a different order.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from app.agent import nodes
from app.agent.nodes import AgentState, parse_tests
from app.llm.base import LLMProvider


def run(
    state: AgentState,
    provider: LLMProvider | None = None,
    report_formats: Sequence[str] = ("markdown", "json"),
    analyze: bool = False,
    progress_callback: Callable[[str], None] | None = None,
) -> AgentState:
    """Run the full pipeline over a pre-loaded AgentState and return the final state."""
    state = parse_tests(state, provider=provider)
    state = nodes.execute_tests(state, progress_callback=progress_callback)
    state = nodes.verify_results(state)
    state = nodes.explain_results(state, provider=provider)
    if analyze:
        state = nodes.analyze(state, provider=provider)
    state = nodes.render_report(state, formats=list(report_formats))
    return state
