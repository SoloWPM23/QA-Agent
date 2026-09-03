"""Mocked tests for the M2 parse pipeline (no real LM Studio needed).

Uses respx to fake the /chat/completions endpoint so the orchestration
(LLM -> TestSuite) can be verified deterministically offline.
"""

from __future__ import annotations

import json

import httpx
import respx

from app.core.schemas import TableBlock
from app.input.schemas import TableBlockChunk, TextChunk
from app.llm.client import LMStudioProvider
from app.llm.schemas import AuthConfig

BASE = "http://lm.test"


def _completion(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": content}}]},
    )


def _tc_json(case_id: str, method: str, path: str, status: int) -> str:
    return json.dumps(
        {
            "id": case_id,
            "title": f"Case {case_id}",
            "request": {"method": method, "path": path},
            "expected": {"status": status},
        }
    )


def _provider() -> LMStudioProvider:
    return LMStudioProvider(base_url=f"{BASE}/v1")


def test_parse_test_suite_from_text_chunks():
    chunks = [
        TextChunk(
            text="Test Case TC-001\nID: TC-001\nMethod: GET\nPath: /api/v1/users", source_index=0
        ),
        TextChunk(
            text="Test Case TC-002\nID: TC-002\nMethod: POST\nPath: /api/v1/batch", source_index=1
        ),
    ]
    c1 = _tc_json("TC-001", "GET", "/api/v1/users", 200)
    c2 = _tc_json("TC-002", "POST", "/api/v1/batch", 201)
    with respx.mock(base_url=BASE) as router:
        router.post("/v1/chat/completions").side_effect = [_completion(c1), _completion(c2)]

        suite = _provider().parse_test_suite(chunks, base_url="http://target.test")

    assert suite.base_url == "http://target.test"
    assert len(suite.cases) == 2
    assert [c.id for c in suite.cases] == ["TC-001", "TC-002"]
    assert suite.cases[0].request.method == "GET"
    assert suite.cases[1].request.path == "/api/v1/batch"
    assert all(not c.needs_review for c in suite.cases)


def test_parse_test_suite_injects_auth():
    chunks = [TextChunk(text="Test Case TC-001\nID: TC-001\nMethod: GET\nPath: /x", source_index=0)]
    c = _tc_json("TC-001", "GET", "/x", 200)
    auth = AuthConfig(type="bearer", token="sekret")
    with respx.mock(base_url=BASE) as router:
        router.post("/v1/chat/completions").return_value = _completion(c)
        suite = _provider().parse_test_suite(chunks, base_url="http://target.test", auth=auth)
    assert suite.auth is not None
    assert suite.auth.type == "bearer"
    assert suite.auth.token == "sekret"


def test_parse_merges_chunk_review_not_overwritten():
    block = TableBlock(
        test_case_label="Test Case TC-00X",
        fields={"ID": "TC-00X", "Method": "", "Path": ""},
        source_index=0,
        needs_review=True,
        review_reason="Field wajib tidak ada.",
    )
    chunks = [TableBlockChunk(block=block)]
    c = _tc_json("TC-00X", "GET", "/x", 200)
    with respx.mock(base_url=BASE) as router:
        router.post("/v1/chat/completions").return_value = _completion(c)
        suite = _provider().parse_test_suite(chunks, base_url="http://target.test")

    case = suite.cases[0]
    assert case.needs_review is True
    assert "Field wajib tidak ada" in case.review_reason


def test_parse_tableblock_renders_to_prompt():
    block = TableBlock(
        test_case_label="Test Case TC-020",
        fields={"ID": "TC-020", "Method": "DELETE", "Path": "/api/v1/items/5"},
        source_index=0,
    )
    chunks = [TableBlockChunk(block=block)]
    c = _tc_json("TC-020", "DELETE", "/api/v1/items/5", 204)
    with respx.mock(base_url=BASE) as router:
        route = router.post("/v1/chat/completions")
        route.return_value = _completion(c)
        suite = _provider().parse_test_suite(chunks, base_url="http://target.test")

    assert suite.cases[0].request.method == "DELETE"
    body = route.calls[-1].request.content.decode()
    assert "Test Case TC-020" in body
    assert "Path: /api/v1/items/5" in body


def test_parse_empty_text_skipped():
    chunks = [TextChunk(text="   ", source_index=0)]
    with respx.mock(base_url=BASE) as router:
        suite = _provider().parse_test_suite(chunks, base_url="http://target.test")
        # No requests should be made for empty text.
        assert not router.calls
    assert suite.cases == []
