from uuid import uuid4

from sqlalchemy import select

from rag.models import Issue


def create_device(client, name="Device A"):
    response = client.post(
        "/api/devices",
        json={
            "name": name,
            "model": "X100",
            "manufacturer": "Siemens",
            "description": "Industrial electrical device",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_device_crud_duplicates_filters(client):
    device = create_device(client)
    assert client.get("/api/devices/" + device["id"]).json()["name"] == "Device A"
    assert (
        client.post(
            "/api/devices", json={"name": "device a", "model": "x100", "manufacturer": "siemens"}
        ).status_code
        == 409
    )
    create_device(client, "Device B")
    result = client.get(
        "/api/devices", params={"name": "A", "model": "x100", "manufacturer": "Siemens", "limit": 1}
    ).json()
    assert result["total"] == 1 and len(result["items"]) == 1
    data = {
        "name": "Device Updated",
        "model": "X200",
        "manufacturer": "Siemens",
        "metadata": {"location": "lab"},
    }
    assert client.put("/api/devices/" + device["id"], json=data).json()["model"] == "X200"
    assert client.delete("/api/devices/" + device["id"]).status_code == 204
    assert client.get("/api/devices/" + device["id"]).status_code == 404


def test_issue_crud_embedding_updates_and_hypothesis(client, embeddings, database):
    device = create_device(client)
    data = {
        "device_id": device["id"],
        "title": "Clicking during startup",
        "category": "Sound",
        "symptoms": "Repetitive clicking when powered on",
        "possible_cause": "Defective relay",
    }
    response = client.post("/api/issues", json=data)
    assert response.status_code == 201
    issue = response.json()
    assert issue["possible_cause_confirmed"] is False
    assert embeddings.calls == 1
    assert client.post("/api/issues", json=data).status_code == 409
    count = embeddings.calls
    assert client.put("/api/issues/" + issue["id"], json=data).status_code == 200
    assert embeddings.calls == count
    with database.session() as session:
        before = list(session.scalar(select(Issue)).embedding)
    data["symptoms"] = "Overheating motor after extended operation"
    assert client.put("/api/issues/" + issue["id"], json=data).status_code == 200
    with database.session() as session:
        assert list(session.scalar(select(Issue)).embedding) != before
    result = client.get(
        "/api/issues", params={"device_id": device["id"], "category": "sound", "symptoms": "motor"}
    ).json()
    assert result["total"] == 1
    assert client.get("/api/issues/" + issue["id"]).status_code == 200
    assert client.delete("/api/issues/" + issue["id"]).status_code == 204
    assert client.get("/api/issues/" + issue["id"]).status_code == 404


def test_validation_and_foreign_keys(client):
    assert (
        client.post("/api/devices", json={"name": "", "model": "X", "manufacturer": "M"}).status_code == 422
    )
    assert (
        client.post(
            "/api/issues", json={"device_id": str(uuid4()), "title": "T", "category": "C", "symptoms": "S"}
        ).status_code
        == 404
    )
    device = create_device(client)
    data = {"device_id": device["id"], "title": "T", "category": "C", "symptoms": "S"}
    issue = client.post("/api/issues", json=data).json()
    assert client.delete("/api/devices/" + device["id"]).status_code == 204
    assert client.get("/api/issues/" + issue["id"]).status_code == 404
    assert client.get("/api/devices?limit=1000").status_code == 422


def test_device_name_ambiguity_and_literal_search(client):
    first = create_device(client)
    second = client.post(
        "/api/devices", json={"name": "Device A", "model": "X200", "manufacturer": "Siemens"}
    )
    assert second.status_code == 201
    assert client.app.state.knowledge.find_device("Device A")["ambiguous"]
    assert len(client.app.state.knowledge.find_device("Device A", "X100")["matches"]) == 1
    assert client.get("/api/devices?name=%25").json()["total"] == 0
    assert first["id"] != second.json()["id"]
