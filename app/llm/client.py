"""Concrete LLM provider for LM Studio's OpenAI-compatible endpoint.

LM Studio exposes an OpenAI-compatible /v1/chat/completions API. This class
wraps it with httpx, normalizes all transport/HTTP errors into
LLMProviderError (the uniform contract from base.py), and registers itself
so orchestration can look it up by name via get_provider("lm_studio").
"""

from __future__ import annotations

import json

import httpx

from app.llm.base import ChatMessage, LLMProviderError, register
from app.llm.schemas import AuthConfig, TestCase, TestSuite

# Model name loaded into LM Studio, passed as the chat completion model.
_DEFAULT_MODEL = "meta-llama-3.1-8b-instruct"


@register("lm_studio")
class LMStudioProvider:
    """Calls LM Studio's local server using the OpenAI-compatible API."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model: str = _DEFAULT_MODEL,
        timeout: float = 120.0,
    ) -> None:
        """Ctor for an LM Studio provider.

        base_url MUST include the API version path, e.g. "http://localhost:1234/v1"
        (the /v1 is required, not optional). /chat/completions is appended to it.
        The httpx.Client is created once and reused so repeated chat() calls do
        not pay a fresh TCP handshake each time.
        """
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.Client(timeout=timeout)

    def supports_structured_output(self) -> bool:
        """LM Studio 8B usage relies on tolerant parsing, not native schema mode."""
        return False

    def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.0,
        json_mode: bool = True,
    ) -> str:
        """Send the conversation and return the raw assistant text.

        Every failure (connect, timeout, HTTP error, bad payload) is wrapped
        in LLMProviderError so callers see a single, uniform exception type.
        """
        url = f"{self._base_url}/chat/completions"
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        # json_mode is reserved for a future structured-output provider. LM Studio
        # rejects response_format type "json_object" (HTTP 400), so we do NOT send
        # any response_format and instead rely on tolerant parsing (extract_json).
        # Keeping json_mode in the signature keeps the LLMProvider contract stable.
        _ = json_mode

        # Transport failures (timeout, connection drop) are retried a couple of
        # times here, since a busy local model may briefly exceed the timeout.
        # This is the provider-level retry the parsing layer explicitly
        # delegates to (see parse_with_retry docstring).
        last_exc: Exception | None = None
        try:
            for _ in range(3):
                try:
                    resp = self._client.post(url, json=payload)
                    break
                except (httpx.TimeoutException, httpx.ConnectError) as exc:
                    last_exc = exc
            else:
                raise LLMProviderError(
                    f"Gagal menghubungi LM Studio di {url}: {last_exc}"
                ) from last_exc
        except httpx.HTTPError as exc:
            # Any other transport error (network, proxy, redirect, etc.) is
            # surfaced as the uniform LLMProviderError, per the base contract.
            raise LLMProviderError(f"Gagal menghubungi LM Studio di {url}: {exc}") from exc

        # Non-timeout HTTP errors (e.g. malformed payload) propagate directly.
        try:
            resp.raise_for_status()  # 4xx/5xx -> HTTPStatusError.
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"LM Studio mengembalikan status {resp.status_code}: {resp.text[:300]}"
            ) from exc

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise LLMProviderError("Respons LM Studio bukan JSON yang valid") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                f"Respons LM Studio tidak memiliki choices[0].message.content: {exc}"
            ) from exc

        if not isinstance(content, str):
            raise LLMProviderError("Konten pesan LM Studio bukan string")
        return content

    def parse_test_suite(
        self,
        chunks: list[object],
        base_url: str,
        auth: AuthConfig | None = None,
    ) -> TestSuite:
        """Translate a list of chunks (from the input layer) into a TestSuite.

        Each chunk is rendered to plain text, sent to the LLM via
        build_case_prompt + parse_with_retry, and validated into a TestCase.
        Chunk-level structural flags (e.g. a TableBlock that declared
        needs_review during M1 parsing) are merged into the resulting
        TestCase and never overwritten by the LLM.

        base_url and auth come from the user, not the LLM.
        """
        from app.input.chunker import chunk_to_text
        from app.llm.parsing import parse_with_retry
        from app.llm.prompt_builder import build_case_prompt

        cases: list[TestCase] = []
        for chunk in chunks:
            text = chunk_to_text(chunk)
            if not text.strip():
                continue
            try:
                case = parse_with_retry(self, build_case_prompt(text), TestCase)
            except LLMProviderError as exc:
                # A total LLM failure for a single chunk must not kill the run;
                # surface it as a needs_review placeholder (non-blocking).
                case = TestCase(
                    id="",
                    title="",
                    needs_review=True,
                    review_reason=f"Gagal mem-parsing chunk: {exc}",
                )
            self._merge_chunk_review(case, chunk)
            cases.append(case)
        return TestSuite(base_url=base_url, auth=auth, cases=cases)

    @staticmethod
    def _merge_chunk_review(case: TestCase, chunk: object) -> None:
        """Fold a chunk's non-blocking review flag into the parsed TestCase."""
        chunk_flagged = False
        chunk_reason: str | None = None
        if hasattr(chunk, "block") and hasattr(chunk.block, "needs_review"):
            block = chunk.block
            chunk_flagged = bool(getattr(block, "needs_review", False))
            chunk_reason = getattr(block, "review_reason", None)
        elif hasattr(chunk, "needs_review"):
            chunk_flagged = bool(getattr(chunk, "needs_review", False))
            chunk_reason = getattr(chunk, "review_reason", None)

        if chunk_flagged:
            parts = [r for r in (chunk_reason, case.review_reason) if r]
            case.needs_review = True
            case.review_reason = " | ".join(parts) if parts else "Chunk ditandai perlu review."
