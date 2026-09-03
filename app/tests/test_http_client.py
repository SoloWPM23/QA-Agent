"""Tests for HTTP executors and auth handlers (deterministic, no LLM).

A tiny in-process HTTP server is started in a background thread to exercise
HttpxExecutor against real request/response behavior (status, JSON body,
query string, auth headers, method routing).
"""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.llm.schemas import AuthConfig, HttpRequest
from app.runner.base import get_auth_handler, get_executor
from app.runner.http_client import HttpxExecutor, apply_auth, join_url


class _Handler(BaseHTTPRequestHandler):
    def _respond(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw_body = self.rfile.read(length) if length else b""

        query = {}
        if "?" in self.path:
            for pair in self.path.split("?", 1)[1].split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    query.setdefault(k, []).append(v)

        auth = self.headers.get("Authorization", "")
        payload = {
            "method": self.command,
            "path": self.path.split("?", 1)[0],
            "query": query,
            "auth": auth,
            "body": json.loads(raw_body) if raw_body else None,
        }
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Echo", "1")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    do_GET = _respond
    do_POST = _respond
    do_PUT = _respond
    do_PATCH = _respond
    do_DELETE = _respond

    def log_message(self, *args):  # silence
        pass


@pytest.fixture(scope="module")
def server_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    port = srv.server_address[1]
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


def test_join_url_variants():
    assert join_url("http://x/api", "/v1/u") == "http://x/api/v1/u"
    assert join_url("http://x/api/", "v1") == "http://x/api/v1"
    assert join_url("http://x", "/v1") == "http://x/v1"


def test_httpx_executor_get_with_query(server_url):
    req = HttpRequest(method="GET", path="/api/users", query={"limit": "10", "tag": ["a", "b"]})
    result = HttpxExecutor().call(req, base_url=server_url)
    assert result.status_code == 200
    assert result.body["method"] == "GET"
    assert result.body["path"] == "/api/users"
    assert sorted(result.body["query"]["tag"]) == ["a", "b"]
    assert result.headers["x-echo"] == "1"


def test_httpx_executor_post_json_body(server_url):
    req = HttpRequest(method="POST", path="/items", body={"name": "x", "qty": 2})
    result = HttpxExecutor().call(req, base_url=server_url)
    assert result.body["method"] == "POST"
    assert result.body["body"] == {"name": "x", "qty": 2}


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_httpx_executor_other_methods(server_url, method):
    req = HttpRequest(method=method, path="/thing")
    result = HttpxExecutor().call(req, base_url=server_url)
    assert result.body["method"] == method


def test_apply_auth_basic_sets_header():
    req = HttpRequest(method="GET", path="/x")
    apply_auth(req, AuthConfig(type="basic", username="u", password="p"))
    expected = "Basic " + base64.b64encode(b"u:p").decode()
    assert req.headers["Authorization"] == expected


def test_apply_auth_bearer():
    req = HttpRequest(method="GET", path="/x")
    apply_auth(req, AuthConfig(type="bearer", token="t"))
    assert req.headers["Authorization"] == "Bearer t"


def test_apply_auth_api_key_header_value():
    req = HttpRequest(method="GET", path="/x")
    apply_auth(req, AuthConfig(type="api_key", header_name="X-Key", token="abc"))
    assert req.headers["X-Key"] == "abc"


def test_apply_auth_none_no_header():
    req = HttpRequest(method="GET", path="/x")
    apply_auth(req, AuthConfig(type="none"))
    assert req.headers == {}


def test_apply_auth_basic_missing_creds_skips():
    req = HttpRequest(method="GET", path="/x")
    apply_auth(req, AuthConfig(type="basic"))
    assert "Authorization" not in req.headers


def test_registry_resolves_executors():
    assert get_executor("httpx") is HttpxExecutor
    assert get_executor("playwright").__name__ == "PlaywrightExecutor"


def test_registry_resolves_auth_handlers():
    assert get_auth_handler("none").__name__ == "NoAuthHandler"
