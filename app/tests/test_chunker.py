"""Tests for the chunker: docx tables -> one chunk each, text -> sliced."""

from __future__ import annotations

from app.core.schemas import TableBlock
from app.input import chunker
from app.input.schemas import TableBlockChunk, TextChunk


def _blocks():
    return [
        TableBlock(test_case_label="Test Case TC-001", fields={"ID": "TC-001"}, source_index=0),
        TableBlock(test_case_label="Test Case TC-002", fields={"ID": "TC-002"}, source_index=1),
        TableBlock(test_case_label="Test Case TC-003", fields={"ID": "TC-003"}, source_index=2),
    ]


def test_chunk_blocks_one_per_table():
    chunks = chunker.chunk_blocks(_blocks())
    assert len(chunks) == 3
    assert all(isinstance(c, TableBlockChunk) for c in chunks)
    assert [c.block.source_index for c in chunks] == [0, 1, 2]


def test_chunk_blocks_preserves_order():
    # Deliberately unsorted input; chunker re-sorts by source_index.
    blocks = list(reversed(_blocks()))
    chunks = chunker.chunk_blocks(blocks)
    assert [c.block.source_index for c in chunks] == [0, 1, 2]


def test_chunk_text_splits_on_tc_markers():
    text = (
        "Test Case TC-010: ambil user\n\nID: TC-010\n\n"
        "Test Case TC-011: update user\n\nID: TC-011\n"
    )
    chunks = chunker.chunk_text(text)
    assert len(chunks) == 2
    assert chunks[0].text.startswith("Test Case TC-010")
    assert chunks[1].text.startswith("Test Case TC-011")
    assert chunks[0].source_index == 0
    assert chunks[1].source_index == 1


def test_chunk_text_no_marker_single_chunk():
    chunks = chunker.chunk_text("Ini dokumen tanpa test case sama sekali.")
    assert len(chunks) == 1
    assert isinstance(chunks[0], TextChunk)
    assert chunks[0].source_index == 0


def test_chunk_text_empty():
    assert chunker.chunk_text("   ") == []
    assert chunker.chunk_text("") == []


def test_chunk_text_too_large_segment_split():
    text = "Test Case TC-001: A\n\n" + "x" * 200 + "\n\n" + "y" * 3000
    chunks = chunker.chunk_text(text, max_chars=1000)
    # One marker + oversized body must be split into multiple chunks.
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.text) <= 1000


def test_block_to_text_renders_table():
    block = TableBlock(
        test_case_label="Test Case TC-001",
        fields={"ID": "TC-001", "Method": "GET", "Path": "/api/v1/users"},
        source_index=0,
    )
    text = chunker.block_to_text(block)
    assert text.startswith("Test Case TC-001")
    assert "ID: TC-001" in text
    assert "Method: GET" in text
    assert "Path: /api/v1/users" in text
    assert text.count("\n") == 3  # header + 3 fields


def test_chunk_to_text_table_vs_text():
    block = TableBlock(test_case_label="Test Case TC-001", fields={"ID": "TC-001"})
    tb_chunk = TableBlockChunk(block=block)
    assert chunker.chunk_to_text(tb_chunk) == "Test Case TC-001\nID: TC-001"

    tx_chunk = TextChunk(text="plain", source_index=0)
    assert chunker.chunk_to_text(tx_chunk) == "plain"
