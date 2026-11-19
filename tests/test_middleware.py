"""Rate limiting and compression."""

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from orbispanora_api.middleware import GZipMiddleware, RateLimitMiddleware
from orbispanora_api.middleware.rate_limiter import RateLimiter


def run(coroutine):
    return asyncio.run(coroutine)


class TestRateLimiter:

    def test_allows_up_to_the_limit_then_refuses(self):
        limiter = RateLimiter(requests=2, window=60)
        assert run(limiter.is_allowed("1.2.3.4")) == (True, 1)
        assert run(limiter.is_allowed("1.2.3.4")) == (True, 0)
        assert run(limiter.is_allowed("1.2.3.4")) == (False, 0)

    def test_clients_are_counted_separately(self):
        limiter = RateLimiter(requests=1, window=60)
        assert run(limiter.is_allowed("1.2.3.4"))[0] is True
        assert run(limiter.is_allowed("5.6.7.8"))[0] is True

    def test_old_requests_leave_the_window(self):
        limiter = RateLimiter(requests=1, window=60)
        limiter._requests["1.2.3.4"] = [0.0]
        assert run(limiter.is_allowed("1.2.3.4"))[0] is True

    def test_cleanup_removes_idle_clients(self):
        limiter = RateLimiter(requests=5, window=60)
        limiter._requests["old"] = [0.0]
        run(limiter.is_allowed("recent"))
        run(limiter.cleanup_old_entries())
        assert list(limiter._requests) == ["recent"]


def app_with(*middlewares):
    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"text": "x" * 2000}

    @app.get("/docs-like")
    def docs_like():
        return {"text": "x" * 2000}

    for middleware, options in middlewares:
        app.add_middleware(middleware, **options)
    return app


class TestRateLimitMiddleware:

    def test_headers_report_the_remaining_requests(self):
        client = TestClient(app_with((RateLimitMiddleware, {"requests": 5, "window": 60})))
        response = client.get("/ping")
        assert response.headers["X-RateLimit-Limit"] == "5"
        assert response.headers["X-RateLimit-Remaining"] == "4"

    def test_disabled_adds_no_headers(self):
        client = TestClient(app_with((RateLimitMiddleware, {"requests": 5, "window": 60, "enabled": False})))
        assert "X-RateLimit-Limit" not in client.get("/ping").headers


class TestCompression:

    def test_large_responses_are_compressed(self):
        client = TestClient(app_with((GZipMiddleware, {"minimum_size": 100})))
        assert client.get("/ping", headers={"Accept-Encoding": "gzip"}).headers["content-encoding"] == "gzip"

    def test_documentation_paths_are_not_compressed(self):
        app = FastAPI()
        app.add_middleware(GZipMiddleware, minimum_size=1)
        client = TestClient(app)
        assert "content-encoding" not in client.get("/docs", headers={"Accept-Encoding": "gzip"}).headers
