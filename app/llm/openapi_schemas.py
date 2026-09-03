"""Schemas for OpenAPI to test suite conversion."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GeneratedTestCase(BaseModel):
    """One test case generated from an OpenAPI operation."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default="TC-001")
    judul: str = ""
    deskripsi: str = ""
    method: str = ""
    path: str = ""
    headers: str = "(tidak ada)"
    query_params: str = "(tidak ada)"
    body: str = "(tidak ada)"
    expected_status_code: str = ""
    expected_schema: str = "(tidak ada)"
    jsonpath_checks: str = "(tidak ada)"
    regex: str = "(tidak ada)"
    contains: str = "(tidak ada)"


class ConversionResult(BaseModel):
    """Result of converting an OpenAPI spec into test cases."""

    model_config = ConfigDict(extra="forbid")

    cases: list[GeneratedTestCase] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
