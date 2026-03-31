from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import threading
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import Settings
from ..services.auth_service import decode_access_token
from ..services.public_demo_audit import PublicDemoAuditLogger


@dataclass(frozen=True)
class _RateRule:
    bucket: str
    window_seconds: int
    max_requests: int


class _InMemoryWindowRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, deque[float]] = {}

    def allow(self, *, key: str, rule: _RateRule) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            cutoff = now - max(1, int(rule.window_seconds))
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= max(1, int(rule.max_requests)):
                retry_after = max(1, int(bucket[0] + int(rule.window_seconds) - now + 0.999))
                return False, retry_after
            bucket.append(now)
            if not bucket:
                self._buckets.pop(key, None)
            return True, 0


class PublicDemoRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, settings: Settings) -> None:  # noqa: ANN001
        super().__init__(app)
        self._settings = settings
        self._limiter = _InMemoryWindowRateLimiter()
        self._demo_route = str(getattr(settings, "public_demo_route", "/demo") or "/demo").rstrip("/") or "/demo"
        self._audit = PublicDemoAuditLogger(
            enabled=bool(getattr(settings, "public_demo_audit_enabled", True)),
            path=getattr(settings, "public_demo_audit_log_path"),
        )

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        path = request.url.path
        method = request.method.upper()
        is_demo_route = self._is_demo_route(path)
        is_demo_token = False if path == "/api/auth/demo" else self._is_public_demo_token(request)
        rule = self._match_rule(path=path, method=method, is_demo_token=is_demo_token)
        if rule is not None:
            client_ip = self._client_ip(request)
            allowed, retry_after = self._limiter.allow(key=f"{rule.bucket}:{client_ip}", rule=rule)
            if not allowed:
                self._audit.log(
                    event="demo_rate_limited",
                    request=request,
                    status_code=429,
                    extra={"bucket": rule.bucket, "retry_after": retry_after},
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "公开演示访问过于频繁，请稍后再试"},
                    headers={"Retry-After": str(retry_after)},
                )
        response = await call_next(request)
        self._audit_response(
            request=request,
            path=path,
            method=method,
            is_demo_route=is_demo_route,
            is_demo_token=is_demo_token,
            rule=rule,
            status_code=int(response.status_code),
        )
        return response

    def _match_rule(self, *, path: str, method: str, is_demo_token: bool) -> _RateRule | None:
        if not bool(getattr(self._settings, "public_demo_enabled", False)):
            return None

        if path == "/api/auth/demo":
            return _RateRule(
                bucket="demo-auth",
                window_seconds=int(getattr(self._settings, "public_demo_auth_window_seconds", 300)),
                max_requests=int(getattr(self._settings, "public_demo_auth_max_requests", 20)),
            )

        if method in {"OPTIONS", "HEAD"}:
            return None

        if not is_demo_token:
            return None

        if path in {"/api/files/upload-file", "/api/files/upload-image"}:
            return _RateRule(
                bucket="demo-upload",
                window_seconds=int(getattr(self._settings, "public_demo_upload_window_seconds", 600)),
                max_requests=int(getattr(self._settings, "public_demo_upload_max_requests", 12)),
            )

        if path.startswith("/api/skills/pipeline/") or path == "/api/chat":
            return _RateRule(
                bucket="demo-pipeline",
                window_seconds=int(getattr(self._settings, "public_demo_pipeline_window_seconds", 600)),
                max_requests=int(getattr(self._settings, "public_demo_pipeline_max_requests", 12)),
            )

        if method not in {"GET"}:
            return _RateRule(
                bucket="demo-write",
                window_seconds=int(getattr(self._settings, "public_demo_write_window_seconds", 300)),
                max_requests=int(getattr(self._settings, "public_demo_write_max_requests", 30)),
            )

        return None

    def _audit_response(
        self,
        *,
        request: Request,
        path: str,
        method: str,
        is_demo_route: bool,
        is_demo_token: bool,
        rule: _RateRule | None,
        status_code: int,
    ) -> None:
        if is_demo_route and method == "GET":
            self._audit.log(event="demo_route_hit", request=request, status_code=status_code)
            return

        if path == "/api/auth/demo":
            self._audit.log(event="demo_auth_issued", request=request, status_code=status_code)
            return

        if not is_demo_token:
            return

        if path in {"/api/files/upload-file", "/api/files/upload-image"}:
            self._audit.log(
                event="demo_upload_request",
                request=request,
                status_code=status_code,
                extra={"bucket": rule.bucket if rule else "demo-upload"},
            )
            return

        if path.startswith("/api/skills/pipeline/") or path == "/api/chat":
            self._audit.log(
                event="demo_pipeline_request",
                request=request,
                status_code=status_code,
                extra={"bucket": rule.bucket if rule else "demo-pipeline"},
            )
            return

        if method != "GET":
            self._audit.log(
                event="demo_write_request",
                request=request,
                status_code=status_code,
                extra={"bucket": rule.bucket if rule else "demo-write"},
            )

    def _is_demo_route(self, path: str) -> bool:
        if path == self._demo_route:
            return True
        return bool(self._demo_route not in {"", "/"} and path.startswith(f"{self._demo_route}/"))

    def _is_public_demo_token(self, request: Request) -> bool:
        auth = str(request.headers.get("authorization") or "").strip()
        if not auth.lower().startswith("bearer "):
            return False
        token = auth[7:].strip()
        if not token:
            return False
        try:
            return bool(decode_access_token(settings=self._settings, token=token).is_public_demo)
        except Exception:
            return False

    @staticmethod
    def _client_ip(request: Request) -> str:
        client = getattr(request, "client", None)
        host = str(getattr(client, "host", "") or "").strip()
        return host or "unknown"
