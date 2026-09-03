"""LLM provider abstraction and connection registry.

The entire orchestration layer relies solely on this protocol, so
adding a new provider (OpenAI-compatible, Ollama, etc.) does not require
modifying the orchestration code at all.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypedDict, runtime_checkable


class ChatMessage(TypedDict):
    """A message in an LLM conversation. TypedDict so that typos in keys are caught during type checking."""

    role: str
    content: str


class LLMProviderError(Exception):
    """A uniform error for all LLM failures.

    Each provider MUST wrap the original error (timeout, rate limit,
    malformed response, etc.) in this exception before passing it on, so that
    the orchestration layer can handle failures uniformly without
    knowing the details of each provider’s HTTP library.
    """


@runtime_checkable
class LLMProvider(Protocol):
    """A standard contract that all LLM backends must comply with."""

    def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.0,
        json_mode: bool = True,
    ) -> str:
        """Send the conversation; return the raw response text as a string. All failures must be thrown as LLMProviderError."""
        ...

    def supports_structured_output(self) -> bool:
        """This is true if the backend can constrain the output to conform to the JSON schema."""
        ...


# Name registry (normalized to lowercase) -> class provider.
LLM_PROVIDERS: dict[str, type[LLMProvider]] = {}


def _normalize(name: str) -> str:
    """Normalize provider names to make them case-insensitive."""
    return name.strip().lower()


def _meets_contract(cls: type) -> bool:
    """True if the class has all the methods required by the protocol.

    Note: The `issubclass` method on `Protocol` only checks for the existence of method names,
    not signature matching—a limitation inherent to `typing.Protocol`.
    """
    if not isinstance(cls, type):
        return False
    return issubclass(cls, LLMProvider)


def register(name: str) -> Callable[[type[LLMProvider]], type[LLMProvider]]:
    """Decorator: Register a class as a provider with a unique name."""

    def decorator(cls: type[LLMProvider]) -> type[LLMProvider]:
        key = _normalize(name)
        # Duplicate name = registry bug, fail early (fail-fast).
        if key in LLM_PROVIDERS:
            raise ValueError(f"Provider sudah terdaftar: {name!r}")
        # Structural validation during registration, not when called.
        if not _meets_contract(cls):
            raise TypeError(
                f"{cls.__name__} tidak memenuhi kontrak LLMProvider "
                "(kurang method chat dan/atau supports_structured_output?)"
            )
        LLM_PROVIDERS[key] = cls
        return cls

    return decorator


def get_provider(name: str) -> type[LLMProvider]:
    """Get the class provider by name; return an explicit error if it is unknown."""
    key = _normalize(name)
    if key not in LLM_PROVIDERS:
        raise KeyError(f"Provider tidak dikenal: {name!r}. Terdaftar: {sorted(LLM_PROVIDERS)}")
    return LLM_PROVIDERS[key]
