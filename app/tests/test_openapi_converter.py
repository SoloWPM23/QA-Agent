"""Tests for OpenAPI to test suite conversion."""

from __future__ import annotations

import pytest

from app.llm.openapi_converter import load_openapi_content, sanitize_cases
from app.llm.openapi_schemas import GeneratedTestCase


class FakeChatProvider:
    """A minimal LLM provider for converter tests."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict], temperature: float = 0.0, json_mode: bool = True) -> str:
        self.calls.append(messages)
        return self.content

    def supports_structured_output(self) -> bool:
        return False


def test_load_openapi_content_parses_json():
    raw = '{"openapi": "3.0.0", "paths": {}}'
    result = load_openapi_content(raw)
    assert '"openapi": "3.0.0"' in result


def test_load_openapi_content_parses_yaml():
    raw = "openapi: 3.0.0\npaths: {}"
    result = load_openapi_content(raw)
    assert '"openapi": "3.0.0"' in result


def test_load_openapi_content_rejects_invalid():
    with pytest.raises(ValueError):
        load_openapi_content("not valid json or yaml: [")


def test_sanitize_cases_fixes_invalid_ids_and_methods():
    cases = [
        GeneratedTestCase(id="", method="get", path="api/users"),
        GeneratedTestCase(id="TC-005", method="TRACE", path="/api/users"),
    ]
    result = sanitize_cases(cases)
    assert result[0].id == "TC-001"
    assert result[0].method == "GET"
    assert result[0].path == "/api/users"
    assert result[1].id == "TC-005"
    assert result[1].method == "GET"


def test_convert_openapi_to_suite_parses_llm_output():
    from app.llm.openapi_converter import convert_openapi_to_suite

    provider = FakeChatProvider(
        '{"cases": [{"id": "TC-001", "judul": "Get users", "deskripsi": "", '
        '"method": "GET", "path": "/api/v1/users", "headers": "(tidak ada)", '
        '"query_params": "(tidak ada)", "body": "(tidak ada)", '
        '"expected_status_code": "200", "expected_schema": "users (array)", '
        '"jsonpath_checks": "$.users", "regex": "(tidak ada)", '
        '"contains": "(tidak ada)"}], "failed": []}'
    )
    result = convert_openapi_to_suite(provider, "{}")
    assert len(result.cases) == 1
    assert result.cases[0].id == "TC-001"
    assert result.cases[0].method == "GET"


def test_convert_openapi_to_suite_captures_failed_endpoints():
    from app.llm.openapi_converter import convert_openapi_to_suite

    provider = FakeChatProvider('{"cases": [], "failed": ["POST /unknown: unsupported schema"]}')
    result = convert_openapi_to_suite(provider, "{}")
    assert len(result.cases) == 0
    assert len(result.failed) == 1
