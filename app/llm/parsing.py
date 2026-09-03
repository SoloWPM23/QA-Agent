"""Tolerant JSON extraction and retry logic for LLM output.

A local LLM almost never returns pure JSON: it adds prose, code fences,
or trailing text. This module isolates all the "messy" handling -- stripping
fences, extracting the first valid JSON value, and retrying with an explicit
correction message when the output fails to parse or to validate.
"""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.llm.base import LLMProvider, LLMProviderError

# Number of correction rounds after the first attempt at the parsing layer.
# This constant controls how many times the parser asks the LLM to fix a
# malformed JSON/schema response. It is intentionally separate from
# ``AppConfig.max_retries`` (default 3), which is the global budget that the
# provider-level retry may also consume for transient transport failures.
MAX_RETRIES = 2

# Matches a markdown fenced block, e.g. ```json {...} ``` (language optional).
_FENCE_RE = re.compile(r"```[a-zA-Z]*\s*(.*?)```", re.DOTALL)
_JSON_START = re.compile(r"[\[{]")

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class ParseRetryError(Exception):
    """Internal signal to trigger another attempt with a correction message."""


class ParseError(LLMProviderError):
    """Raised when the LLM output cannot be parsed/validated after all retries."""


def extract_json(raw: str) -> Any:
    """Extract the first valid JSON value from arbitrary LLM text."""
    text = raw.strip()
    if not text:
        raise ValueError("Respons LLM kosong - tidak ada JSON untuk diekstrak.")

    # 1) Fast path: the whole text is already valid JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) Prefer the LAST markdown fence, so an example block echoed from the
    #    prompt is not mistaken for the actual answer the LLM produces.
    fenced = _strip_fences(text)
    if fenced != text:
        try:
            return json.loads(fenced)
        except json.JSONDecodeError:
            pass
        text = fenced

    # 3) Strip JS-style comments (local models annotate JSON with // comments),
    #    then try the parsing paths again from the top of this function scope.
    commented = _strip_js_comments(text)
    if commented != text:
        try:
            return json.loads(commented)
        except json.JSONDecodeError:
            pass
        text = commented

    # 4) Fallback: pick the LONGEST balanced value that parses, so a corrupted
    #    outer object (with // comments already stripped above) does not leak a
    #    small nested value like {} as a silent wrong-data success.
    candidate = _largest_balanced_value(text)
    if candidate is not None:
        return json.loads(candidate)

    raise ValueError("Gagal mengekstrak JSON dari respons LLM.")


def validation_feedback(exc: ValidationError) -> str:
    """Human-readable schema errors, used as the correction hint for retries."""
    lines = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"])
        lines.append(f"- {loc}: {err['msg']} (type={err['type']})")
    return "Validasi skema gagal pada field berikut:\n" + "\n".join(lines)


def parse_with_retry(
    provider: LLMProvider,
    messages: list[dict],
    model: type[_ModelT],
) -> _ModelT:
    """Send chat messages, parse to model, retrying with explicit corrections.

    Every failed attempt appends a correction message to a working copy of
    the conversation, so the LLM sees exactly what went wrong. After
    MAX_RETRIES the original failure is re-raised as ParseError.

    Note: retry here ONLY reacts to format/schema errors (ParseRetryError).
    Transport failures (timeout, rate limit, etc.) raised by provider.chat()
    as LLMProviderError propagate immediately and are NOT retried at this
    level -- that responsibility belongs to the provider itself.
    """
    working = list(messages)

    @retry(
        stop=stop_after_attempt(MAX_RETRIES + 1),
        wait=wait_fixed(0.5),
        retry=retry_if_exception_type(ParseRetryError),
        reraise=True,
    )
    def attempt() -> _ModelT:
        raw = provider.chat(working, temperature=0.0, json_mode=True)
        try:
            data = extract_json(raw)
        except ValueError as exc:  # JSONDecodeError is a subclass of ValueError.
            feedback = f"JSON tidak valid: {exc}"
            working.append(_correction_message(feedback))
            raise ParseRetryError(feedback) from exc

        try:
            return model.model_validate(data)  # extra=forbid errors surface here.
        except ValidationError as exc:
            feedback = validation_feedback(exc)
            working.append(_correction_message(feedback))
            raise ParseRetryError(feedback) from exc

    try:
        return attempt()
    except ParseRetryError as exc:
        raise ParseError(
            f"Gagal memvalidasi respons LLM setelah {MAX_RETRIES} koreksi: {exc}"
        ) from exc


def _strip_fences(text: str) -> str:
    """Return content of the LAST markdown fenced block, or the raw text.

    The last occurrence is used deliberately: when the prompt itself contains
    an example JSON fence, the LLM often echoes it before producing the real
    answer, so the first fence would be the wrong one.
    """
    match = list(_FENCE_RE.finditer(text))
    return match[-1].group(1).strip() if match else text


def _strip_js_comments(text: str) -> str:
    """Remove // line and /* */ block comments outside of string literals.

    Local models often annotate their JSON output with // comments (e.g.
    "method": "TRACE" // Perlu diubah). Standard json.loads rejects these, so
    we strip them while carefully skipping anything inside a "..." string.
    """
    out = []
    i = 0
    n = len(text)
    in_string = False
    escaped = False
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "/":  # line comment -> drop until newline.
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":  # block comment -> drop until */.
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue

        out.append(ch)
        i += 1
    return "".join(out)


def _all_balanced_values(text: str) -> list[str]:
    """Return every balanced bracket-delimited value that parses as JSON.

    Scans char by char, skipping string literals (with escapes) so braces
    inside text like "a { b }" do not break the bracket counting. Returns a
    list of candidate JSON strings in scan order.
    """
    candidates: list[str] = []
    for start in _JSON_START.finditer(text):
        open_idx = start.start()
        depth = 0
        in_string = False
        escaped = False

        for i in range(open_idx, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
                # Unbalanced closer at this start point means scanning further
                # is pointless and risks O(n^2); move on to the next candidate.
                if depth < 0:
                    break
                if depth == 0:
                    candidate = text[open_idx : i + 1]
                    try:
                        json.loads(candidate)
                        candidates.append(candidate)
                    except json.JSONDecodeError:
                        pass  # Nested value that did not stand alone; keep scanning.
                    break
        else:
            if depth > 0:
                raise ValueError("Terdapat bracket yang tidak seimbang dalam respons LLM.")
    return candidates


def _largest_balanced_value(text: str) -> str | None:
    """Return the longest parseable JSON value, preferring the full object.

    A corrupted outer object (e.g. one with // comments) may fail to parse
    whole, and the scanner would otherwise return a small nested value like
    `{}` from inside it. Picking the longest valid candidate avoids this
    silent wrong-data success.
    """
    candidates = _all_balanced_values(text)
    return max(candidates, key=len) if candidates else None


def _correction_message(feedback: str) -> dict:
    """Build a user message that tells the LLM exactly how to fix its output."""
    return {
        "role": "user",
        "content": (
            "Response sebelumnya TIDAK VALID dan ditolak oleh sistem. "
            "Jangan ulangi kesalahan yang sama. Perbaiki dan kembalikan SEMUA "
            "data dalam satu objek JSON valid.\n"
            "Aturan penting: JANGAN menulis komentar (// atau /* */) di dalam "
            "JSON. Untuk nilai yang tidak valid pada field ber-constraint "
            "(misal method), Pilih nilai valid yang paling mendekati "
            '(GET/POST/PUT/PATCH/DELETE), set "needs_review": true, dan '
            'jelaskan nilai asli dari dokumen di "review_reason".\n'
            f"Detail error:\n{feedback}"
        ),
    }
