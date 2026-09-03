"""Convert an OpenAPI spec into a structured test suite using an LLM."""

from __future__ import annotations

import json
from typing import Any

from app.llm.base import LLMProvider, LLMProviderError
from app.llm.openapi_schemas import ConversionResult, GeneratedTestCase
from app.llm.parsing import parse_with_retry
from app.llm.prompt_builder import build_openapi_convert_prompt


def convert_openapi_to_suite(
    provider: LLMProvider,
    openapi_content: str,
) -> ConversionResult:
    """Convert an OpenAPI JSON/YAML string into a list of test cases."""
    try:
        result = parse_with_retry(
            provider,
            build_openapi_convert_prompt(openapi_content),
            ConversionResult,
        )
        return result
    except LLMProviderError as exc:
        raise LLMProviderError(f"Failed to convert OpenAPI spec: {exc}") from exc


def load_openapi_content(raw: str | bytes) -> str:
    """Return the OpenAPI content as a string, parsing YAML if needed."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")

    text = raw.strip()
    if text.startswith("{"):
        return text

    try:
        import yaml

        data = yaml.safe_load(text)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as exc:
        raise ValueError(f"OpenAPI spec is not valid JSON or YAML: {exc}") from exc


def sanitize_cases(cases: list[GeneratedTestCase]) -> list[GeneratedTestCase]:
    """Ensure generated cases have valid IDs and methods."""
    sanitized: list[GeneratedTestCase] = []
    for idx, case in enumerate(cases, start=1):
        updates: dict[str, Any] = {}
        if not case.id or not case.id.startswith("TC-"):
            updates["id"] = f"TC-{idx:03d}"
        method = case.method.upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            method = "GET"
        updates["method"] = method
        if case.path and not case.path.startswith("/"):
            updates["path"] = "/" + case.path
        sanitized.append(case.model_copy(update=updates))
    return sanitized
