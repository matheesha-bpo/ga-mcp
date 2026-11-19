"""Shared-secret gateway around Google's official Google Analytics MCP server.

Google's `analytics-mcp` HTTP mode expects every caller to send its own Google
OAuth token. This gateway instead:

* runs the official tools unchanged (read-only, `allow_write=False`);
* uses the Cloud Run service account (Application Default Credentials) for
  every Google API call, so no Google login is needed in Claude;
* lets a request in only when it carries the shared secret, the same way the
  Meta Ads MCP does: `?key=<MCP_SECRET>` or `Authorization: Bearer <MCP_SECRET>`.

The secret is removed from the request before the official server sees it.
That matters: the official server treats any `Authorization: Bearer` header as
a Google access token.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qsl, urlencode

from mcp.server.transport_security import TransportSecuritySettings

import analytics_mcp.coordinator as coordinator

logger = logging.getLogger("ga_mcp_gateway")

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

MCP_PATH = "/mcp"
HEALTH_PATH = "/healthz"


def _secret() -> str:
    return (os.environ.get("MCP_SECRET") or "").strip()


def _provided_key(scope: Scope) -> str:
    query = scope.get("query_string", b"").decode("latin-1")
    for name, value in parse_qsl(query, keep_blank_values=True):
        if name == "key" and value:
            return value
    for raw_name, raw_value in scope.get("headers", []):
        name = raw_name.decode("latin-1").lower()
        value = raw_value.decode("latin-1").strip()
        if name == "authorization" and value.lower().startswith("bearer "):
            return value[7:].strip()
        if name == "x-mcp-key" and value:
            return value
    return ""


def is_authorized(scope: Scope) -> bool:
    secret = _secret()
    provided = _provided_key(scope)
    if not secret or not provided:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), secret.encode("utf-8"))


def strip_credentials(scope: Scope) -> Scope:
    """Returns a copy of the scope without our secret in the query or headers."""
    query = scope.get("query_string", b"").decode("latin-1")
    kept = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k != "key"]
    headers = [
        (name, value)
        for name, value in scope.get("headers", [])
        if name.decode("latin-1").lower() not in ("authorization", "x-mcp-key")
    ]
    return {**scope, "query_string": urlencode(kept).encode("latin-1"), "headers": headers}


async def _json(send: Send, status: int, body: dict[str, Any]) -> None:
    payload = json.dumps(body).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


class SharedSecretGateway:
    """ASGI middleware: health check, shared-secret auth, credential stripping."""

    def __init__(self, inner: ASGIApp) -> None:
        self.inner = inner

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # Lifespan events start the MCP session manager.
            await self.inner(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == HEALTH_PATH:
            await _json(send, 200, {"ok": True})
            return

        if path not in (MCP_PATH, MCP_PATH + "/"):
            await _json(send, 404, {"error": "not_found"})
            return

        if not is_authorized(scope):
            await _json(send, 401, {"error": "unauthorized"})
            return

        await self.inner(strip_credentials(scope), receive, send)


def build_app() -> ASGIApp:
    if os.environ.get("ANALYTICS_MCP_ALLOW_WRITE", "").strip().lower() in ("1", "true", "yes", "on"):
        raise RuntimeError("This gateway is read-only. Unset ANALYTICS_MCP_ALLOW_WRITE.")
    if not _secret():
        logger.warning("MCP_SECRET is not set: every MCP request will be refused.")

    server = coordinator.create_server(allow_write=False, require_request_credentials=False)
    inner = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",
        # Cloud Run sets the Host header to its own URL. The shared secret is
        # the access control, so DNS-rebinding protection is not needed.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    return SharedSecretGateway(inner)


app = build_app()
