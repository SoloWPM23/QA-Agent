"""Convert a raw document structure (from an adapter) into Chunk units.

Rules:
- docx (list[TableBlock]): one table becomes one TableBlockChunk; document
  order is preserved via source_index.
- text (str): split on test-case markers (TC-XXX on its own line), bound each
  slice to a rough size, and produce TextChunk items. Text with no marker at
  all becomes a single TextChunk.
"""

from __future__ import annotations

import re

from app.core.schemas import TableBlock
from app.input.schemas import Chunk, TableBlockChunk, TextChunk

# Matches a test-case header line, e.g. "Test Case TC-001" (flexible whitespace).
_TC_SPLIT_RE = re.compile(r"(?m)^Test\s+Case\s+TC-\d{3}\b")

# Rough character budget per slice (a loose stand-in for token budget).
_CHUNK_MAX_CHARS = 2500


def chunk_blocks(blocks: list[TableBlock]) -> list[Chunk]:
    """Turn parsed docx tables into one chunk each, order preserved."""
    # Re-index defensively so callers can't break order.
    ordered = sorted(blocks, key=lambda b: b.source_index)
    return [TableBlockChunk(block=b) for b in ordered]


def chunk_text(
    text: str,
    max_chars: int = _CHUNK_MAX_CHARS,
) -> list[Chunk]:
    """Split raw text into TextChunk slices, one per test-case block."""
    stripped = text.strip()
    if not stripped:
        return []

    matches = list(_TC_SPLIT_RE.finditer(stripped))
    if not matches:
        return [_to_text_chunk(stripped, 0)]

    chunks: list[Chunk] = []
    index = 0
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(stripped)
        segment = stripped[start:end]
        for part in _split_too_large(segment, max_chars):
            chunks.append(_to_text_chunk(part, index))
            index += 1
    return chunks


def _split_too_large(segment: str, max_chars: int = _CHUNK_MAX_CHARS) -> list[str]:
    """Split a too-large segment into <= max_chars pieces on newline boundaries."""
    if len(segment) <= max_chars:
        return [segment]
    parts: list[str] = []
    while len(segment) > max_chars:
        cut = segment.rfind("\n", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        parts.append(segment[:cut])
        segment = segment[cut:].lstrip("\n")
    if segment:
        parts.append(segment)
    return parts


def _to_text_chunk(text: str, source_index: int) -> Chunk:
    return TextChunk(text=text, source_index=source_index)


def block_to_text(block: TableBlock) -> str:
    """Render a TableBlock back into a plain-text table representation.

    This is the form handed to the LLM parser: header row "Test Case TC-XXX"
    followed by "Label: value" lines. It intentionally mirrors the layout of
    the source .docx table so the model can map labels back to fields.
    """
    lines = [block.test_case_label]
    for label, value in block.fields.items():
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


def chunk_to_text(chunk: Chunk) -> str:
    """Convert any Chunk to its plain-text form for the LLM parser."""
    if chunk.kind == "table_block":
        return block_to_text(chunk.block)
    return chunk.text
