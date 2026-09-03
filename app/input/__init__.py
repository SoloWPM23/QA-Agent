"""Input layer: turn uploaded test-suite documents into Chunk units.

Importing this package triggers adapter registration (docx, text, pdf) so the
dispatcher can find them by extension.
"""

from __future__ import annotations

from app.input import adapter, base, chunker, docx_adapter, schemas, text_adapter
from app.input.adapter import load_document
from app.input.base import get_adapter, register
from app.input.schemas import Chunk, TableBlockChunk, TextChunk

__all__ = [
    "Chunk",
    "TableBlockChunk",
    "TextChunk",
    "adapter",
    "base",
    "chunker",
    "docx_adapter",
    "get_adapter",
    "load_document",
    "register",
    "schemas",
    "text_adapter",
]
