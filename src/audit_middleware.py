import json
import logging
import os
import time
import uuid

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send


LOGGER = logging.getLogger("vllm_server.audit")


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class RequestAuditMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.enabled = env_flag("AUDIT_LOG_ENABLED", True)
        self.log_paths = {
            item.strip()
            for item in os.getenv(
                "AUDIT_LOG_PATHS",
                "/v1/chat/completions,/v1/completions,/v1/responses",
            ).split(",")
            if item.strip()
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path not in self.log_paths:
            await self.app(scope, receive, send)
            return

        started_at = time.perf_counter()
        headers = Headers(scope=scope)
        client = scope.get("client")
        request_id = headers.get("x-request-id") or uuid.uuid4().hex
        if headers.get("x-request-id") is None:
            scope["headers"] = list(scope["headers"]) + [
                (b"x-request-id", request_id.encode("utf-8"))
            ]
            headers = Headers(scope=scope)
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        error_type = None
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            error_type = exc.__class__.__name__
            raise
        finally:
            payload = {
                "event": "llm_request",
                "request_id": request_id,
                "method": scope.get("method"),
                "path": path,
                "status_code": status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "client_ip": headers.get("x-forwarded-for") or (client[0] if client else None),
                "content_length": headers.get("content-length"),
                "user_agent": headers.get("user-agent"),
                "error_type": error_type,
            }
            LOGGER.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))
