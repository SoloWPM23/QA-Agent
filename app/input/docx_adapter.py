"""docx document adapter: parse tables following the standard template.

Each table in the template follows the shape: row 0 is the header labelled
"Test Case TC-XXX", and rows 1..N are key/value field pairs (ID, Judul,
Method, Path, ...). This adapter extracts each test-case table into a
TableBlock with the ORIGINAL Indonesian labels as keys (parsing/translation
to Pydantic fields is the LLM's job later).

It also runs lightweight deterministic STRUCTURAL validation (header shape,
row count, ID pattern) and flags anomalies via needs_review -- it never judges
the MEANING of the content.
"""

from __future__ import annotations

from app.core.schemas import TEST_CASE_HEADER_MARKER, TableBlock
from app.input.base import register

# Field labels that a well-formed test-case table is expected to carry.
_REQUIRED_FIELDS = ("ID", "Judul", "Method", "Path", "Expected Status Code")


@register("docx")
class DocxAdapter:
    """Extract test-case tables from a .docx file into TableBlock objects."""

    extensions = ("docx",)

    def extract(self, path: str) -> list[TableBlock]:
        try:
            from docx import Document
        except ImportError as exc:  # pragma: no cover - env has python-docx.
            raise ValueError("python-docx tidak terinstal; tidak bisa membaca .docx") from exc

        doc = Document(path)
        blocks: list[TableBlock] = []
        source_index = 0
        for table in doc.tables:
            rows = self._rows(table)
            if not self._is_test_case(rows):
                # A non-test-case table (e.g. the template's reference table)
                # is skipped silently, not flagged.
                continue
            block = self._to_table_block(rows, source_index)
            blocks.append(block)
            source_index += 1
        return blocks

    @staticmethod
    def _rows(table) -> list[list[str]]:
        """Normalize a python-docx table into a list of [label, value] rows."""
        result = []
        for row in table.rows:
            # The template merges cells so both columns often repeat the same
            # label; dedupe consecutive duplicate cells within a row.
            cells = []
            for cell in row.cells:
                text = cell.text.strip()
                if not cells or cells[-1] != text:
                    cells.append(text)
            result.append(cells)
        return result

    @staticmethod
    def _is_test_case(rows: list[list[str]]) -> bool:
        """Return True when a table looks like a test case, not a reference table."""
        if not rows:
            return False
        header = rows[0][0] if rows[0] else ""
        # Reference table (row 0 = "Tipe" etc.) does not contain the marker.
        return TEST_CASE_HEADER_MARKER in header

    @staticmethod
    def _to_table_block(rows: list[list[str]], source_index: int) -> TableBlock:
        header = rows[0][0] if rows and rows[0] else ""
        fields: dict[str, str] = {}
        for row in rows[1:]:
            if not row:
                continue
            label = row[0]
            value = row[1] if len(row) > 1 else ""
            # Last label wins if duplicated, keeps behavior predictable.
            fields[label] = value

        block = TableBlock(
            test_case_label=header,
            fields=fields,
            source_index=source_index,
        )

        # --- Structural validation (shape only, not meaning) ---
        reasons = []
        if not block.case_id:
            reasons.append("Label header bukan pola 'Test Case TC-XXX' (ID tidak valid).")
        missing = [f for f in _REQUIRED_FIELDS if f not in fields]
        if missing:
            reasons.append(f"Field wajib tidak ada: {', '.join(missing)}.")
        empty_required = [f for f in _REQUIRED_FIELDS if f in fields and not fields[f].strip()]
        if empty_required:
            reasons.append(f"Field wajib kosong: {', '.join(empty_required)}.")
        path = fields.get("Path", "")
        if "{" in path and "}" in path:
            reasons.append(f"Path berisi placeholder parameter: {path}.")
        if reasons:
            block.needs_review = True
            block.review_reason = " ".join(reasons)
        return block
