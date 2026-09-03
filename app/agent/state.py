"""Temporary state model passed between pipeline stages.

AgentState is the single data bag the orchestrator carries from input to
report. It is deliberately thin (PLAN 3): it only holds data, never logic.
New fields added later MUST have defaults so existing code keeps running
(backward-compatible discipline, PLAN 12.3).

chunks are the input-layer output (M1); injected at run time. test_cases and
suite are the parsed LLM output (M2). results/verdicts are filled by the
executor/verifier in M3. attempt/max_attempts support the retry fallback.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.llm.schemas import AuthConfig, TestCase, TestCaseResult, TestSuite, Verdict


class AgentState(BaseModel):
    """Mutable run state, shared across pipeline nodes."""

    model_config = ConfigDict(extra="forbid")

    # Input layer.
    chunks: list[Any] = Field(default_factory=list)
    spec_text: str = ""

    # User-provided run config.
    base_url: str = ""
    auth: AuthConfig | None = None
    provider_config: dict[str, str] | None = None

    # Parsed (M2) results.
    test_cases: list[TestCase] = Field(default_factory=list)
    suite: TestSuite | None = None

    # Execution (M3) & verification (M3) results.
    results: list[TestCaseResult] = Field(default_factory=list)
    verdicts: list[Verdict] = Field(default_factory=list)

    # Fallback / retry bookkeeping.
    attempt: int = 0
    max_attempts: int = 1
    stdout_report: str | None = None

    # Optional LLM analyst output (M4), keyed by case_id.
    analysis: dict[str, Any] = Field(default_factory=dict)
