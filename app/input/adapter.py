"""Top-level dispatcher: load a document into Chunk units.

load_document(path, doc_format=None) picks the right adapter by file
extension (or an explicit format when supplied), runs its extract(), then
runs the chunker to normalize the result into a uniform list[Chunk].
"""

from __future__ import annotations

import os

from app.core.schemas import TableBlock
from app.input.base import get_adapter
from app.input.chunker import chunk_blocks, chunk_text
from app.input.schemas import Chunk, TextChunk


def load_document(path: str, doc_format: str | None = None) -> list[Chunk]:
    """Load a document at path into a list of chunks.

    doc_format optionally overrides the extension-based detection (e.g. when
    the caller knows the real format regardless of the filename).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"File tidak ditemukan: {path}")

    ext = _resolve_ext(doc_format, path)
    adapter_class = get_adapter(ext)

    try:
        raw = adapter_class().extract(path)
    except ValueError as exc:
        # A text extractor that could not produce text (e.g. a scan-only PDF
        # without OCR) surfaces as a single needs_review TextChunk so the
        # pipeline keeps going instead of crashing.
        return [
            TextChunk(
                kind="text",
                text="",
                needs_review=True,
                review_reason=str(exc),
            )
        ]

    if isinstance(raw, list):
        if raw and not isinstance(raw[0], TableBlock):
            raise TypeError(
                f"Adapter {ext!r} mengembalikan list non-TableBlock; kontrak dilanggar."
            )
        return chunk_blocks(raw)

    return chunk_text(raw)


def _resolve_ext(doc_format: str | None, path: str) -> str:
    if doc_format:
        return doc_format.lower().lstrip(".")
    return os.path.splitext(path)[1].lstrip(".").lower()
