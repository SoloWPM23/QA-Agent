"""Chunk types produced by the input layer.

A chunk is the unit of work handed to the LLM translation stage: either a
parsed docx table (TableBlockChunk) or a slice of plain text
(TextChunk, from txt/md/pdf). The discriminated union is keyed on "kind".

This module imports ONLY from app.core -- never from app.llm -- to honour the
input-layer isolation rule and avoid a dependency cycle.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.core.schemas import TableBlock


class TableBlockChunk(BaseModel):
    """One docx table, kept as one chunk (1 table = 1 test case)."""

    kind: Literal["table_block"] = "table_block"
    block: TableBlock


class TextChunk(BaseModel):
    """A slice of plain text (from txt/md/pdf) to send for translation."""

    kind: Literal["text"] = "text"
    text: str
    source_index: int = 0
    needs_review: bool = False
    review_reason: str | None = None


Chunk = TableBlockChunk | TextChunk
