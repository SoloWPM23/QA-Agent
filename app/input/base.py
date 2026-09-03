"""DocumentAdapter contract and registry.

Every concrete document adapter (docx, text, pdf) implements this protocol and
registers itself in DOCUMENT_FORMATS, so the dispatcher can look it up purely
by file extension. Adding a new format later means adding one adapter class and
registering it -- no changes to the dispatcher or the rest of the pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.core.schemas import TableBlock


class DocumentAdapter(Protocol):
    """Uniform contract for turning a document on disk into a raw structure.

    extract() returns list[TableBlock] for tabular formats (docx) or a str of
    raw text for plain-text formats (txt/md/pdf). All errors should be raised
    as ValueError with a clear message so the dispatcher can normalize them.
    """

    extensions: list[str]

    def extract(self, path: str) -> list[TableBlock] | str:
        """Read the file at path and return its raw structured representation."""
        ...


# Registry: normalized extension -> adapter class.
DOCUMENT_FORMATS: dict[str, type[DocumentAdapter]] = {}


def _normalize(ext: str) -> str:
    """Normalize an extension to lowercase without dots."""
    return ext.strip().lower().lstrip(".")


def _meets_contract(cls: type) -> bool:
    """True when the class provides the extract method and an extensions attr.

    Inspected manually (not via issubclass on the Protocol) because a Protocol
    with a data attribute like "extensions" does not support runtime_checkable
    issubclass checks.
    """
    if not isinstance(cls, type):
        return False
    extract = getattr(cls, "extract", None)
    return callable(extract) and hasattr(cls, "extensions")


def register(ext: str) -> Callable[[type[DocumentAdapter]], type[DocumentAdapter]]:
    """Decorator: register an adapter for one or more comma-separated extensions."""

    def decorator(cls: type[DocumentAdapter]) -> type[DocumentAdapter]:
        for raw in ext.split(","):
            key = _normalize(raw)
            if not raw:
                continue
            if key in DOCUMENT_FORMATS:
                raise ValueError(f"Adapter sudah terdaftar untuk ekstensi {key!r}")
            if not _meets_contract(cls):
                raise TypeError(
                    f"{cls.__name__} tidak memenuhi kontrak DocumentAdapter "
                    "(kurang method extract dan/atau atribut extensions?)"
                )
            DOCUMENT_FORMATS[key] = cls
        return cls

    return decorator


def get_adapter(ext: str) -> type[DocumentAdapter]:
    """Return the adapter class for an extension; error if unknown."""
    key = _normalize(ext)
    if key not in DOCUMENT_FORMATS:
        raise KeyError(
            f"Format dokumen tidak didukung: {key!r}. Terdaftar: {sorted(DOCUMENT_FORMATS)}"
        )
    return DOCUMENT_FORMATS[key]
