"""Plain-text document adapters for .txt, .md, and .pdf.

txt/md are read raw as UTF-8 text. pdf is read via pypdf and its pages joined
into a single string. If a PDF yields no extractable text at all (e.g. a scan
without OCR), extract raises ValueError so the dispatcher can surface it as a
needs_review chunk instead of silently sending empty text downstream.
"""

from __future__ import annotations

from app.input.base import register

_ENCODING = "utf-8"
_ENCODING_ERRORS = "ignore"


@register("txt,md")
class TextAdapter:
    """Read a plain-text document (txt/md) as a raw string."""

    extensions = ("txt", "md")

    def extract(self, path: str) -> str:
        with open(path, encoding=_ENCODING, errors=_ENCODING_ERRORS) as fh:
            return fh.read()


@register("pdf")
class PdfAdapter:
    """Extract text from a PDF, joining all pages into one string."""

    extensions = ("pdf",)

    def extract(self, path: str) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - env has pypdf pinned.
            raise ValueError("pypdf tidak terinstal; tidak bisa membaca PDF") from exc

        reader = PdfReader(path)
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 - per-page resilience.
                parts.append("")
        text = "\n".join(parts).strip()

        if not text:
            raise ValueError(
                "PDF tidak berisi teks yang bisa diekstrak (mungkin hasil scan tanpa OCR)."
            )
        return text
