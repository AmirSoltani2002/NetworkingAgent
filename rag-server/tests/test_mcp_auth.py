import json
from uuid import uuid4

from fastapi.testclient import TestClient

from rag.api import create_app
from rag.config import Settings
from tests.test_retrieval import seed


def rpc(client, method, params=None, identifier=1, headers=None):
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": identifier, "method": method, "params": params or {}},
        headers={
            "Host": "localhost:8090",
            "Accept": "application/json, text/event-stream",
            **(headers or {}),
        },
    )


def test_mcp_streamable_http_tools_and_shared_retrieval(client, database, embeddings):
    a, b, c, issues, docs, chunk = seed(client, database, embeddings)
    init = rpc(
        client,
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1"},
        },
    )
    assert init.status_code == 200 and init.json()["result"]["serverInfo"]["name"] == "Local RAG Evidence"
    tools = rpc(client, "tools/list").json()["result"]["tools"]
    assert {tool["name"] for tool in tools} == {
        "find_device",
        "get_device_issues",
        "search_knowledge",
        "get_document_context",
    }
    assert all(tool["annotations"]["readOnlyHint"] for tool in tools)
    for name, args in [
        ("find_device", {"name": "Device A"}),
        ("get_device_issues", {"device_id": a["id"]}),
        ("search_knowledge", {"query": "relay startup clicking", "device_id": a["id"]}),
        ("get_document_context", {"chunk_ids": [chunk["chunk_id"]]}),
    ]:
        result = rpc(client, "tools/call", {"name": name, "arguments": args}).json()["result"]
        assert not result.get("isError", False), result
        assert isinstance(result["structuredContent"], dict)
        if name == "search_knowledge":
            rest = client.post("/api/retrieval/search", json={**args, "top_k": 10}).json()
            assert result["structuredContent"]["results"] == rest["results"]
    error = rpc(
        client, "tools/call", {"name": "search_knowledge", "arguments": {"query": "x", "top_k": 1000}}
    ).json()["result"]
    assert error["isError"] and "INVALID_SEARCH" in error["content"][0]["text"]
    assert rpc(client, "tools/list", headers={"Host": "evil.invalid"}).status_code == 421


def test_authentication_rest_mcp_docs_and_health(database, embeddings, tmp_path):
    key = uuid4().hex + uuid4().hex
    settings = Settings(storage_dir=tmp_path, auth_required=True, api_key=key)
    with TestClient(create_app(settings, embeddings, database)) as client:
        for path in ["/api/devices", "/api/issues", "/api/documents"]:
            response = client.get(path)
            assert response.status_code == 401 and response.headers["X-Request-ID"]
            assert key not in response.text
            assert client.get(path, headers={"Authorization": f"Bearer {key}"}).status_code == 200
        assert rpc(client, "tools/list").status_code == 401
        assert rpc(client, "tools/list", headers={"Authorization": f"Bearer {key}"}).status_code == 200
        assert client.get("/docs").status_code == 200
        assert "BearerAuth" in client.get("/openapi.json").json()["components"]["securitySchemes"]
        assert client.get("/health").status_code == 200 and client.get("/ready").status_code == 200
        assert (
            client.post(
                "/api/devices", json={"name": key}, headers={"Authorization": f"Bearer {key}"}
            ).status_code
            == 422
        )


def test_request_size_and_request_id(client):
    response = client.post("/api/devices", content="{}", headers={"Content-Length": str(100 * 1024 * 1024)})
    assert response.status_code == 413 and response.headers["X-Request-ID"]
    bad = client.post("/api/retrieval/search", json={"query": ""})
    assert bad.status_code == 422 and bad.json()["request_id"] == bad.headers["X-Request-ID"]


def test_observability_redacts_library_text():
    import logging

    from rag.observability import JsonFormatter

    record = logging.LogRecord("third.party", logging.ERROR, "", 0, "secret document contents", (), None)
    output = JsonFormatter().format(record)
    assert "secret document" not in output
    assert json.loads(output)["event"] == "library_log"


def test_chunked_request_limit(database, embeddings, tmp_path):
    settings = Settings(storage_dir=tmp_path, auth_required=False, max_upload_mb=1)
    with TestClient(create_app(settings, embeddings, database)) as client:
        response = client.post(
            "/api/devices",
            content=iter([b"x" * 600000, b"x" * 600000]),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413
