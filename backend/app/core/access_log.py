import logging
import time
from datetime import UTC, datetime
from typing import Any

from app.core.database import AsyncSessionLocal
from app.models.audit import AccessLog

logger = logging.getLogger("dxscan.access")

# Noise that would otherwise dominate the table.
_SKIP_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect", "/favicon.ico"}


async def persist(entry: dict[str, Any]) -> None:
    """Writes one access-log row in its own session. Never raises: logging must not break a request."""
    try:
        async with AsyncSessionLocal() as session:
            session.add(AccessLog(**entry))
            await session.commit()
    except Exception:
        logger.exception("Falha ao gravar access log (event=%s path=%s)", entry.get("event"), entry.get("path"))


async def log_auth_event(event: str, username: str | None, client_ip: str | None, user_agent: str | None, detail: str | None = None) -> None:
    await persist({
        "created_at": datetime.now(UTC),
        "event": event,
        "principal_type": "user",
        "principal": username,
        "client_ip": client_ip,
        "user_agent": (user_agent or "")[:300] or None,
        "detail": detail,
    })


class AccessLogMiddleware:
    """Pure ASGI middleware that records every HTTP request (method, path, status, duration, who).

    The "who" comes from ``request.state.principal`` / ``principal_type``, which the auth dependencies
    set (see app/core/security.py). Starlette keeps request.state in ``scope["state"]``, the same dict
    this middleware reads after the app has answered.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in _SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        status_holder = {"code": 500}  # stays 500 if the app crashes before sending headers
        started = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            client = scope.get("client")
            entry = {
                "created_at": datetime.now(UTC),
                "event": "http_request",
                "principal_type": state.get("principal_type", "anonymous"),
                "principal": state.get("principal"),
                "method": scope["method"],
                "path": scope["path"][:500],
                "status_code": status_holder["code"],
                "duration_ms": round(duration_ms, 2),
                "client_ip": client[0] if client else None,
                "user_agent": headers.get("user-agent", "")[:300] or None,
                "detail": state.get("access_detail"),
            }
            logger.info(
                "%s %s %s %s %.1fms", entry["principal"] or "-", entry["method"], entry["path"],
                entry["status_code"], duration_ms,
            )
            await persist(entry)
