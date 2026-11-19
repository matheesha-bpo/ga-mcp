import os

os.environ["MCP_SECRET"] = "test-secret-value"

from starlette.testclient import TestClient  # noqa: E402

import pytest  # noqa: E402

from ga_mcp_gateway.app import app, is_authorized, strip_credentials  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # The MCP session manager can start only once per process.
    with TestClient(app) as c:
        yield c

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


def scope(query: bytes = b"", headers=None):
    return {"type": "http", "path": "/mcp", "query_string": query, "headers": headers or []}


def test_health_needs_no_key(client):
    assert client.get("/healthz").json() == {"ok": True}


def test_rejects_missing_and_wrong_key(client):
    assert client.post("/mcp", json=INIT, headers=HEADERS).status_code == 401
    assert client.post("/mcp?key=nope", json=INIT, headers=HEADERS).status_code == 401
    wrong = {**HEADERS, "authorization": "Bearer nope"}
    assert client.post("/mcp", json=INIT, headers=wrong).status_code == 401


def test_unknown_path_is_404(client):
    assert client.get("/admin?key=test-secret-value").status_code == 404


def test_accepts_query_key_and_lists_official_tools(client):
    init = client.post("/mcp?key=test-secret-value", json=INIT, headers=HEADERS)
    assert init.status_code == 200, init.text
    listed = client.post("/mcp?key=test-secret-value", json=LIST, headers=HEADERS)
    assert listed.status_code == 200, listed.text
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert "run_report" in names
    assert "get_account_summaries" in names
    assert "run_realtime_report" in names


def test_accepts_bearer_key(client):
    headers = {**HEADERS, "authorization": "Bearer test-secret-value"}
    assert client.post("/mcp", json=INIT, headers=headers).status_code == 200


def test_secret_is_removed_before_official_server():
    s = scope(
        b"key=test-secret-value&x=1",
        [(b"authorization", b"Bearer test-secret-value"), (b"x-mcp-key", b"a"), (b"accept", b"*/*")],
    )
    assert is_authorized(s)
    cleaned = strip_credentials(s)
    assert cleaned["query_string"] == b"x=1"
    assert cleaned["headers"] == [(b"accept", b"*/*")]


def test_empty_secret_refuses_everything(monkeypatch):
    monkeypatch.setenv("MCP_SECRET", "")
    assert not is_authorized(scope(b"key="))
    assert not is_authorized(scope(b"key=anything"))
