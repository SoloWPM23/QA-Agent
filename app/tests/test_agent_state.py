"""Tests for the agent AgentState model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.state import AgentState
from app.core.schemas import TableBlock
from app.input.schemas import TableBlockChunk
from app.llm import schemas as llm


def _case(case_id: str) -> llm.TestCase:
    return llm.TestCase(id=case_id, request=llm.HttpRequest(method="GET", path="/x"))


def test_defaults():
    s = AgentState()
    assert s.base_url == ""
    assert s.chunks == []
    assert s.test_cases == []
    assert s.suite is None
    assert s.auth is None
    assert s.attempt == 0
    assert s.max_attempts == 1


def test_populated():
    block = TableBlock(test_case_label="Test Case TC-001", fields={"ID": "TC-001"})
    s = AgentState(
        base_url="http://target.test",
        auth=llm.AuthConfig(type="none"),
        chunks=[TableBlockChunk(block=block)],
        suite=llm.TestSuite(base_url="http://target.test", cases=[_case("TC-001")]),
        test_cases=[_case("TC-001")],
    )
    assert s.base_url == "http://target.test"
    assert len(s.chunks) == 1
    assert s.suite is not None
    assert s.test_cases[0].id == "TC-001"


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        AgentState(bogus=1)
