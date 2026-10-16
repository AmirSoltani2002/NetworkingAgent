import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tests.test_model import INPUT


def test_auth_validation_health(client, app):
    assert client.get("/health", headers={"Authorization": ""}).status_code == 200
    assert client.get("/ready", headers={"Authorization": ""}).json()["record_count"] == 1000
    for path in ["/api/dataset", "/api/model/metrics", "/mcp", "/openapi.json"]:
        assert client.get(path, headers={"Authorization": ""}).status_code == 401
    assert client.post("/api/model/train", headers={"Authorization": ""}, json={}).status_code == 401
    assert client.post("/api/model/train", json={"use_all_approved_training_data": False}).status_code == 422
    assert client.post("/api/model/train", json={"configuration": {"arbitrary_python": "print(1)"}}).status_code == 422
    assert "x-request-id" in client.get("/api/dataset").headers


@pytest.mark.asyncio
async def test_official_sdk_discovery_all_tools_training_inference_and_errors(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0)); sock.listen(128)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic()+10
    while not server.started and time.monotonic()<deadline:
        await asyncio.sleep(0.02)
    assert server.started
    token = app.state.test_settings.api_key.get_secret_value()
    try:
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http:
            async with streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    assert {t.name for t in tools} == {"get_manufacturing_dataset", "train_quality_model", "get_training_status",
                        "predict_product_quality", "classify_manufacturing_dataset", "get_quality_model_metrics"}
                    assert next(t for t in tools if t.name == "train_quality_model").annotations.readOnlyHint is False
                    assert all(t.inputSchema["additionalProperties"] is False for t in tools)
                    invalid = await session.call_tool("train_quality_model", {"arbitrary_sql": "SELECT 1"})
                    assert invalid.isError
                    invalid = await session.call_tool("predict_product_quality", {**INPUT, "temperature": "82.5"})
                    assert invalid.isError
                    dataset = await session.call_tool("get_manufacturing_dataset", {"limit": 2})
                    assert dataset.structuredContent["total"] == 1000 and len(dataset.structuredContent["items"]) == 2
                    invalid = await session.call_tool("get_manufacturing_dataset", {"limit": 10000})
                    assert invalid.isError
                    job = (await session.call_tool("train_quality_model", {})).structuredContent
                    assert job["status"] in ["queued", "running"]
                    for _ in range(100):
                        status = (await session.call_tool("get_training_status", {"job_id": job["job_id"]})).structuredContent
                        if status["status"] in ["ready", "failed"]: break
                        await asyncio.sleep(0.05)
                    assert status["status"] == "ready" and status["training_sample_count"] == 800
                    prediction = await session.call_tool("predict_product_quality", INPUT)
                    assert prediction.structuredContent["predicted_label"] in [0, 1]
                    invalid = await session.call_tool("predict_product_quality", {**INPUT, "material_quality": 4})
                    assert invalid.isError
                    missing = await session.call_tool("get_training_status", {"job_id": "wrong"})
                    assert missing.isError
                    classified = await session.call_tool("classify_manufacturing_dataset", {"predicted_label": 0, "limit": 3})
                    assert len(classified.structuredContent["items"]) == 3
                    assert classified.structuredContent["statistics"]["population_count"] == 1000
                    metrics = (await session.call_tool("get_quality_model_metrics", {})).structuredContent
                    assert metrics["evaluation_sample_count"] == 200
                    assert metrics["model_version"] == prediction.structuredContent["model_version"]
    finally:
        server.should_exit = True
        await asyncio.to_thread(thread.join, 10)
        sock.close()
