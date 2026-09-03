"""Deterministic mock tests for the LLM transport layer (M6).

Uses ``respx`` to fake the LM Studio ``/chat/completions`` endpoint so the
``LMStudioProvider`` can be tested without a live model.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.llm.base import LLMProviderError
from app.llm.client import LMStudioProvider
from app.llm.parsing import ParseError, parse_with_retry
from app.llm.prompt_builder import build_case_prompt

BASE = "http://lm.test"
URL = f"{BASE}/v1/chat/completions"


def _provider() -> LMStudioProvider:
    return LMStudioProvider(base_url=f"{BASE}/v1")


def _response(content: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        json={"choices": [{"message": {"role": "assistant", "content": content}}]},
    )


def test_chat_returns_content():
    with respx.mock(base_url=BASE) as router:
        router.post("/v1/chat/completions").return_value = _response('{"ok": true}')
        content = _provider().chat([{"role": "user", "content": "hello"}])
    assert content == '{"ok": true}'


def test_chat_raises_on_non_json_body():
    with respx.mock(base_url=BASE) as router:
        router.post("/v1/chat/completions").return_value = httpx.Response(200, text="not json")
        with pytest.raises(LLMProviderError):
            _provider().chat([{"role": "user", "content": "hello"}])


def test_chat_raises_when_content_missing():
    with respx.mock(base_url=BASE) as router:
        router.post("/v1/chat/completions").return_value = httpx.Response(
            200, json={"choices": [{"message": {}}]}
        )
        with pytest.raises(LLMProviderError):
            _provider().chat([{"role": "user", "content": "hello"}])


@pytest.mark.parametrize("status", [400, 401, 500, 503])
def test_chat_raises_on_http_error_status(status):
    with respx.mock(base_url=BASE) as router:
        router.post("/v1/chat/completions").return_value = _response("error", status=status)
        with pytest.raises(LLMProviderError):
            _provider().chat([{"role": "user", "content": "hello"}])


def test_parse_test_suite_with_mocked_chat():
    from app.input.schemas import TextChunk

    content = (
        '{"id": "TC-001", "title": "T", "request": {"method": "GET", "path": "/x"}, '
        '"expected": {"status": 200}}'
    )
    chunks = [
        TextChunk(
            text="Test Case TC-001\nID: TC-001\nMethod: GET\nPath: /x\nExpected Status Code: 200"
        )
    ]
    with respx.mock(base_url=BASE) as router:
        router.post("/v1/chat/completions").return_value = _response(content)
        suite = _provider().parse_test_suite(chunks, base_url="http://target.test")
    assert len(suite.cases) == 1
    assert suite.cases[0].id == "TC-001"
    assert suite.cases[0].request.method == "GET"


def test_parse_with_retry_retries_then_succeeds():
    from app.llm import schemas as llm

    class _Toy(llm.TestCase):
        pass

    good = (
        '{"id": "TC-001", "title": "T", "request": {"method": "GET", "path": "/x"}, "expected": {}}'
    )
    with respx.mock(base_url=BASE) as router:
        router.post("/v1/chat/completions").side_effect = [
            _response("bukan json"),
            _response(good),
        ]
        case = parse_with_retry(
            _provider(),
            build_case_prompt("Test Case TC-001"),
            llm.TestCase,
        )
    assert case.id == "TC-001"


def test_parse_with_retry_raises_after_exhaustion():
    from app.llm import schemas as llm

    with respx.mock(base_url=BASE) as router:
        router.post("/v1/chat/completions").return_value = _response("bukan json")
        with pytest.raises(ParseError):
            parse_with_retry(
                _provider(),
                build_case_prompt("Test Case TC-001"),
                llm.TestCase,
            )
