"""Tests for the input layer's dispatch, adapters, and error handling."""

from __future__ import annotations

import os

import pytest

from app.core.schemas import TableBlock
from app.input import load_document
from app.input.base import DOCUMENT_FORMATS, get_adapter, register
from app.input.schemas import TableBlockChunk, TextChunk

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
DOCX = os.path.join(FIXTURES, "sample_test_suite.docx")
MD = os.path.join(FIXTURES, "sample_suite.md")


# --------------------------------------------------------------------------
# Registry & contract
# --------------------------------------------------------------------------


def test_registered_formats():
    assert {"docx", "txt", "md", "pdf"} <= set(DOCUMENT_FORMATS)


def test_get_adapter_by_extension():
    assert get_adapter("docx").__name__ == "DocxAdapter"
    assert get_adapter("TXT").__name__ == "TextAdapter"


def test_get_adapter_unknown_raises():
    with pytest.raises(KeyError):
        get_adapter("xlsx")


def test_register_rejects_non_contract():
    with pytest.raises(TypeError):

        @register("zzz")
        class _Bad:
            pass


def test_register_rejects_duplicate():
    with pytest.raises(ValueError):

        @register("txt")
        class _Dup:
            extensions = ("txt",)

            def extract(self, path):
                return ""


# --------------------------------------------------------------------------
# docx adapter
# --------------------------------------------------------------------------


def _docx_blocks():
    from app.input.docx_adapter import DocxAdapter

    return DocxAdapter().extract(DOCX)


def test_docx_skips_reference_table():
    blocks = _docx_blocks()
    # Only the two test-case tables remain; reference table (6 rows) is skipped.
    assert len(blocks) == 2


def test_docx_parses_original_labels():
    blocks = _docx_blocks()
    tc = next(b for b in blocks if b.test_case_label == "Test Case TC-001")
    assert tc.case_id == "TC-001"
    assert tc.fields["ID"] == "TC-001"
    assert tc.fields["Method"] == "GET"
    assert tc.fields["Path"] == "/api/v1/users"
    assert tc.fields["Expected Status Code"] == "200"
    assert "Judul" in tc.fields


def test_docx_flag_missing_case_pattern():
    blocks = _docx_blocks()
    templ = next(b for b in blocks if "TC-00X" in b.test_case_label)
    assert templ.case_id == ""
    assert templ.needs_review is True
    assert templ.review_reason is not None


def test_docx_valid_case_not_reviewed():
    blocks = _docx_blocks()
    tc = next(b for b in blocks if b.case_id == "TC-001")
    assert tc.needs_review is False
    assert tc.review_reason is None


# --------------------------------------------------------------------------
# dispatcher
# --------------------------------------------------------------------------


def test_load_docx_returns_table_chunks():
    chunks = load_document(DOCX)
    assert all(isinstance(c, TableBlockChunk) for c in chunks)
    assert len(chunks) == 2
    assert [c.block.case_id for c in chunks] == ["TC-001", ""]


def test_load_text_returns_text_chunks():
    chunks = load_document(MD)
    assert len(chunks) == 2
    assert all(isinstance(c, TextChunk) for c in chunks)
    assert all(not c.needs_review for c in chunks)


def test_load_document_format_override():
    chunks = load_document(MD, doc_format="txt")
    assert all(isinstance(c, TextChunk) for c in chunks)


def test_load_document_missing_file():
    with pytest.raises(FileNotFoundError):
        load_document(os.path.join(FIXTURES, "nope.docx"))


def test_load_document_unknown_format():
    with pytest.raises(KeyError):
        load_document(os.path.join(FIXTURES, "sample.dat"))


def test_load_document_text_failure_becomes_review(monkeypatch):
    # Simulate a text adapter whose extract raised (e.g. scan-only PDF without
    # OCR): load_document must return a needs_review TextChunk, not crash.
    from app.input import base

    class Boom:
        extensions = ("boom",)

        def extract(self, path):
            raise ValueError("PDF tidak berisi teks yang bisa diekstrak.")

    monkeypatch.setitem(base.DOCUMENT_FORMATS, "boom", Boom)
    chunks = load_document(os.path.join(FIXTURES, "sample.dat"), doc_format="boom")
    assert len(chunks) == 1
    c = chunks[0]
    assert isinstance(c, TextChunk)
    assert c.needs_review is True
    assert c.review_reason is not None


# --------------------------------------------------------------------------
# TableBlock core schema
# --------------------------------------------------------------------------


def test_tableblock_case_id_property():
    tb = TableBlock(test_case_label="Test Case TC-042")
    assert tb.case_id == "TC-042"


def test_tableblock_review_defaults():
    tb = TableBlock(test_case_label="Test Case TC-001")
    assert tb.needs_review is False
    assert tb.review_reason is None
