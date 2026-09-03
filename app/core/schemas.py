"""Domain types shared across pipeline layers.

This module is deliberately neutral (not owned by the LLM, input, or runner
layer) so that any layer can import these types without creating a dependency
cycle. Types that are specific to a single concern (e.g. HttpRequest for the
executor) stay in their own layer's schemas module.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# Row label on the first row of every test-case table in the standard template.
TEST_CASE_HEADER_MARKER = "Test Case"


class TableBlock(BaseModel):
    """One parsed table from a .docx document following the standard template.

    case_id is taken from the FIRST TC-ddd match in the header row; if a
    malformed label contains multiple patterns, only the first is used
    (intentional, documented behaviour).

    needs_review is set by the adapter's lightweight deterministic structural
    validation (row count, header shape, ID pattern) -- NOT by the LLM, which
    only interprets meaning at a later stage.
    """

    test_case_label: str = ""
    fields: dict[str, str] = Field(default_factory=dict)
    source_index: int = 0
    needs_review: bool = False
    review_reason: str | None = None

    @property
    def case_id(self) -> str:
        """Extract the first TC-XXX id found in the header row, or empty string."""
        match = re.search(r"TC-\d{3}", self.test_case_label)
        return match.group(0) if match else ""
