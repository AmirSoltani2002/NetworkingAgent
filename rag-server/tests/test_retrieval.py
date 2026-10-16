from uuid import UUID, uuid4

from sqlalchemy import func, select

from rag.models import IssueEvidence
from rag.retrieval import RetrievalService, rrf
from rag.schemas import SearchInput
from tests.test_crud import create_device
from tests.test_documents import upload, worker


def seed(client, database, embeddings):
    a, b = create_device(client), create_device(client, "Device B")
    only_manual = create_device(client, "Device C")
    issues = []
    for device, title, symptoms, cause in [
        (a, "Clicking during startup", "Clicking startup relay", "Worn relay"),
        (a, "Overheating", "Motor overheating cooling fan", "Blocked air intake"),
        (b, "Clicking during startup", "Clicking startup bearing", "Worn bearing"),
    ]:
        issue = client.post(
            "/api/issues",
            json={
                "device_id": device["id"],
                "title": title,
                "category": "Sound" if "Clicking" in title else "Temperature",
                "symptoms": symptoms,
                "possible_cause": cause,
            },
        ).json()
        issues.append(issue)
    docs = []
    for title, devices, content in [
        (
            "Device A Maintenance Manual",
            [a["id"]],
            "# Troubleshooting\nClicking during startup may indicate worn relay contacts. Disconnect power before inspecting relay contacts.",
        ),
        (
            "Device B Troubleshooting Manual",
            [b["id"]],
            "# Troubleshooting\nClicking startup noise may indicate a bearing fault. Inspect motor bearings.",
        ),
        (
            "Shared Relay Manual",
            [a["id"], b["id"]],
            "# Relays\nRelay startup clicking is a supporting observation. Check relay coil voltage and contacts.",
        ),
        (
            "Device C Maintenance Manual",
            [only_manual["id"]],
            "# Cooling\nInspect the cooling fan to prevent overheating during operation.",
        ),
    ]:
        docs.append(upload(client, text=content, devices=devices, title=title).json())
    runner = worker(client, database, embeddings)
    while runner.run_once():
        pass
    first = client.get(f"/api/documents/{docs[0]['id']}/chunks").json()["items"][0]
    assert (
        client.post(
            f"/api/issues/{issues[0]['id']}/evidence",
            json={"chunk_id": first["chunk_id"], "evidence_type": "possible_cause"},
        ).status_code
        == 201
    )
    return a, b, only_manual, issues, docs, first


def test_scoped_hybrid_issues_evidence_and_sources(client, database, embeddings):
    a, b, c, issues, docs, chunk = seed(client, database, embeddings)
    result = client.post(
        "/api/retrieval/search", json={"query": "clicking startup relay", "device_id": a["id"], "top_k": 10}
    ).json()
    assert result["device"]["name"] == "Device A"
    assert result["matched_issues"] and all(item["device_id"] == a["id"] for item in result["matched_issues"])
    assert docs[1]["id"] not in {item["document_id"] for item in result["results"]}
    assert {item["document_id"] for item in result["results"]} <= {docs[0]["id"], docs[2]["id"]}
    result_chunk = next(item for item in result["results"] if item["chunk_id"] == chunk["chunk_id"])
    assert issues[0]["id"] in result_chunk["matched_issue_ids"]
    assert "document_vector" in result_chunk["methods"] and "document_fts" in result_chunk["methods"]
    assert "issue_evidence" in result_chunk["methods"]
    assert result_chunk["document_title"] == "Device A Maintenance Manual"
    assert result_chunk["section_heading"] == "Troubleshooting"
    assert result_chunk["scores"]["rrf_score"] > 0
    assert len({item["chunk_id"] for item in result["results"]}) == len(result["results"])
    assert all(item["possible_cause_confirmed"] is False for item in result["matched_issues"])


def test_direct_documents_without_issues_and_shared_documents(client, database, embeddings):
    a, b, c, issues, docs, chunk = seed(client, database, embeddings)
    direct = client.post(
        "/api/retrieval/search", json={"query": "cooling fan overheating", "device_id": c["id"]}
    ).json()
    assert direct["matched_issues"] == []
    assert direct["results"] and direct["results"][0]["document_id"] == docs[3]["id"]
    for device in [a, b]:
        shared = client.post(
            "/api/retrieval/search",
            json={"query": "relay coil voltage", "device_id": device["id"], "document_ids": [docs[2]["id"]]},
        ).json()
        assert shared["results"] and {item["document_id"] for item in shared["results"]} == {docs[2]["id"]}


def test_filters_broad_search_and_device_disambiguation(client, database, embeddings):
    a, b, c, issues, docs, chunk = seed(client, database, embeddings)
    automatic = client.post("/api/retrieval/search", json={"query": "Device A clicking startup"}).json()
    assert automatic["device_id"] == a["id"]
    broad = client.post("/api/retrieval/search", json={"query": "clicking startup"}).json()
    assert broad["device_id"] is None and broad["results"]
    filtered = client.post(
        "/api/retrieval/search",
        json={
            "query": "overheating cooling",
            "device_id": a["id"],
            "issue_category": "Temperature",
            "document_type": "nonexistent",
        },
    ).json()
    assert all(item["category"] == "Temperature" for item in filtered["matched_issues"])
    assert filtered["results"] == []
    client.post("/api/devices", json={"name": "Device A", "model": "X200", "manufacturer": "Other"})
    ambiguous = client.post("/api/retrieval/search", json={"query": "Device A clicking"})
    assert ambiguous.status_code == 409 and ambiguous.json()["error"]["code"] == "AMBIGUOUS_DEVICE"
    assert (
        client.post(
            "/api/retrieval/search", json={"query": "clicking", "device_id": str(uuid4())}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/retrieval/search", json={"query": "clicking", "document_ids": [str(uuid4())]}
        ).status_code
        == 404
    )
    assert client.post("/api/retrieval/search", json={"query": "clicking", "top_k": 1000}).status_code == 422


def test_explicit_evidence_links_reprocess_and_disassociation(client, database, embeddings):
    a, b, c, issues, docs, chunk = seed(client, database, embeddings)
    evidence = client.get(f"/api/issues/{issues[0]['id']}/evidence").json()
    assert evidence["items"][0]["evidence_type"] == "possible_cause"
    assert (
        client.post(
            f"/api/issues/{issues[2]['id']}/evidence",
            json={"chunk_id": chunk["chunk_id"], "evidence_type": "resolution"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/issues/{issues[0]['id']}/evidence",
            json={"chunk_id": str(uuid4()), "evidence_type": "resolution"},
        ).status_code
        == 404
    )
    assert client.delete(f"/api/issues/{issues[0]['id']}/evidence/{chunk['chunk_id']}").status_code == 204
    assert client.get(f"/api/issues/{issues[0]['id']}/evidence").json()["items"] == []
    client.post(
        f"/api/issues/{issues[0]['id']}/evidence",
        json={"chunk_id": chunk["chunk_id"], "evidence_type": "diagnostic_procedure"},
    )
    client.post(f"/api/documents/{docs[0]['id']}/reprocess")
    worker(client, database, embeddings).run_once()
    assert client.get(f"/api/issues/{issues[0]['id']}/evidence").json()["items"] == []
    new = client.get(f"/api/documents/{docs[0]['id']}/chunks").json()["items"][0]
    client.post(
        f"/api/issues/{issues[0]['id']}/evidence",
        json={"chunk_id": new["chunk_id"], "evidence_type": "resolution"},
    )
    client.put(f"/api/documents/{docs[0]['id']}", json={"device_ids": []})
    assert client.get(f"/api/issues/{issues[0]['id']}/evidence").json()["items"] == []
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(IssueEvidence)) == 0


def test_rrf_and_optional_local_reranker(client, database, embeddings):
    assert rrf([["a", "b", "a"], ["b"]], 60)["b"] > rrf([["a", "b"], ["b"]], 60)["a"]
    a, b, c, issues, docs, chunk = seed(client, database, embeddings)

    class FixtureReranker:
        def scores(self, query, passages):
            return [100 if "coil" in passage else -100 for passage in passages]

    retrieval = RetrievalService(database, client.app.state.settings, embeddings, FixtureReranker())
    result = retrieval.search(SearchInput(query="relay startup clicking", device_id=UUID(a["id"])))
    assert "coil" in result["results"][0]["content"]
    assert all(item["retrieval_method"] == "hybrid_rrf_reranked" for item in result["results"])


def test_not_ready_chunks_are_not_searchable(client, database, embeddings):
    document = upload(client).json()
    worker(client, database, embeddings).run_once()
    client.post(f"/api/documents/{document['id']}/reprocess")
    result = client.post(
        "/api/retrieval/search", json={"query": "relay contacts", "document_ids": [document["id"]]}
    ).json()
    assert result["results"] == []


def test_issue_device_update_prunes_inapplicable_evidence(client, database, embeddings):
    a, b, c, issues, docs, chunk = seed(client, database, embeddings)
    shared_chunk = client.get(f"/api/documents/{docs[2]['id']}/chunks").json()["items"][0]
    client.post(
        f"/api/issues/{issues[0]['id']}/evidence",
        json={"chunk_id": shared_chunk["chunk_id"], "evidence_type": "diagnostic_procedure"},
    )
    moved = client.put(
        f"/api/issues/{issues[0]['id']}",
        json={
            "device_id": b["id"],
            "title": "Moved startup issue",
            "category": "Sound",
            "symptoms": "Clicking startup relay",
            "possible_cause": "Worn relay",
            "description": "",
        },
    )
    assert moved.status_code == 200
    evidence = client.get(f"/api/issues/{issues[0]['id']}/evidence").json()["items"]
    assert {item["document_id"] for item in evidence} == {docs[2]["id"]}
    client.put(f"/api/documents/{docs[2]['id']}", json={"device_ids": [a["id"]]})
    assert client.get(f"/api/issues/{issues[0]['id']}/evidence").json()["items"] == []
