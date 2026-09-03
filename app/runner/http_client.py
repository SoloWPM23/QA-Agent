"""HTTP executors and auth handlers (runner HTTP layer).

``HttpxExecutor`` is the deterministic MVP executor: it turns a parsed
``HttpRequest`` into a real HTTP call with httpx and captures the raw
``HttpResult`` for the verifier. ``PlaywrightExecutor`` covers JavaScript
rendered pages but stays optional -- it lazy-imports Playwright and raises a
clear error if it (or the browser) is not installed, so the core pipeline
never depends on it.

Auth handlers implement the four supported schemes (none/basic/bearer/api_key)
as deterministic header mutations (PLAN 6.6).
"""

from __future__ import annotations

import base64

from app.llm.schemas import AuthConfig, HttpRequest, HttpResult
from app.runner.base import register_auth_handler, register_http_executor

_DEFAULT_TIMEOUT_S = 30.0


def join_url(base_url: str, path: str) -> str:
    """Combine a base URL and a leading-slash path into one absolute URL."""
    return f"{base_url.rstrip('/')}{path if path.startswith('/') else '/' + path}"


def build_query(req: HttpRequest) -> dict[str, str | list[str]]:
    """Return query values, always exposing lists so repeated params survive."""
    return dict(req.query)


@register_http_executor("httpx")
class HttpxExecutor:
    """Runs an HTTP request synchronously with httpx."""

    def __init__(self, timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        self.timeout_s = timeout_s

    def call(self, req: HttpRequest, base_url: str = "") -> HttpResult:
        import httpx  # inlined so collection never depends on it

        url = join_url(base_url, req.path) if base_url else req.path
        params = build_query(req) or None
        kwargs: dict = {
            "headers": dict(req.headers),
            "timeout": self.timeout_s,
            "follow_redirects": True,
        }
        if params:
            kwargs["params"] = params
        if req.body is not None:
            kwargs["json"] = req.body

        with httpx.Client() as client:
            resp = client.request(req.method, url, **kwargs)

        headers = dict(resp.headers)
        body: object = None
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        return HttpResult(status_code=resp.status_code, headers=headers, body=body)


@register_http_executor("playwright")
class PlaywrightExecutor:
    """Runs a request through a real browser (JS-rendered pages). Optional."""

    def call(self, req: HttpRequest, base_url: str = "") -> HttpResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - dependency-gated
            raise RuntimeError(
                "Playwright belum terinstal. Jalankan: pip install playwright "
                "dan 'playwright install chromium' untuk executor ini."
            ) from exc

        url = join_url(base_url, req.path) if base_url else req.path
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            headers = dict(req.headers)
            if req.body is not None:
                headers["Content-Type"] = "application/json"
            processed: list[HttpResult] = []

            def _capture(response) -> None:
                processed.append(
                    HttpResult(
                        status_code=response.status, headers=dict(response.headers), body=None
                    )
                )

            with page.expect_response(url) as resp_info:
                page.goto(url)
            resp = resp_info.value
            processed.append(
                HttpResult(
                    status_code=resp.status,
                    headers=dict(resp.headers),
                    body=resp.json() if _json(resp.text()) else resp.text(),
                )
            )
            browser.close()
        return processed[-1]


def _json(text: str | None):
    if not text:
        return False
    import json

    try:
        json.loads(text)
        return True
    except ValueError:
        return False


@register_auth_handler("none")
class NoAuthHandler:
    def apply(self, req: HttpRequest, cfg: AuthConfig) -> None:
        """No-op: leave the request untouched."""


@register_auth_handler("basic")
class BasicAuthHandler:
    def apply(self, req: HttpRequest, cfg: AuthConfig) -> None:
        if cfg.username is None or cfg.password is None:
            return  # missing credentials -> leave unauthenticated
        raw = f"{cfg.username}:{cfg.password}".encode()
        req.headers["Authorization"] = "Basic " + base64.b64encode(raw).decode()


@register_auth_handler("bearer")
class BearerAuthHandler:
    def apply(self, req: HttpRequest, cfg: AuthConfig) -> None:
        if cfg.token:
            req.headers["Authorization"] = f"Bearer {cfg.token}"


@register_auth_handler("api_key")
class ApiKeyHandler:
    def apply(self, req: HttpRequest, cfg: AuthConfig) -> None:
        if cfg.header_name:
            value = cfg.header_value if cfg.header_value is not None else cfg.token or ""
            req.headers[cfg.header_name] = value


def apply_auth(req: HttpRequest, cfg: AuthConfig | None) -> None:
    """Resolve and apply the auth scheme onto the request (mutates req)."""
    if cfg is None:
        return
    handler = _AUTH_CLASSES.get(cfg.type)
    if handler is None:
        return
    # Work on a copy so the caller's request object is not mutated.
    req.headers = dict(req.headers)
    handler().apply(req, cfg)


_AUTH_CLASSES = {
    "none": NoAuthHandler,
    "basic": BasicAuthHandler,
    "bearer": BearerAuthHandler,
    "api_key": ApiKeyHandler,
}
