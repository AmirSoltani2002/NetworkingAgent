import json
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from reportlab.pdfgen import canvas

from rag.chunking import Chunker, extract, structures
from rag.errors import IngestionError
from rag.models import Document
from rag.worker import IngestionWorker
from tests.test_crud import create_device


def upload(
    client,
    text="# Troubleshooting\n\nWARNING: Isolate power before inspecting the relay.\n\n1. Disconnect power.\n2. Inspect relay contacts.",
    devices=None,
    name="manual.md",
    **fields,
):
    return client.post(
        "/api/documents/upload",
        data={
            "title": "Maintenance Manual",
            "document_type": "manual",
            "device_ids": json.dumps(devices or []),
            **fields,
        },
        files={"file": (name, text.encode(), "text/markdown" if name.endswith(".md") else "text/plain")},
    )


def worker(client, database, embeddings):
    return IngestionWorker(database, client.app.state.settings, embeddings)


def test_upload_relationships_async_duplicate_delete(client, database, embeddings):
    a, b = create_device(client), create_device(client, "Device B")
    response = upload(client, devices=[a["id"], b["id"]], name="../../manual.md")
    assert response.status_code == 202
    document = response.json()
    assert document["status"] == "uploaded" and not document["duplicate"]
    assert set(document["device_ids"]) == {a["id"], b["id"]}
    assert "/" not in document["file_path"]
    assert client.get(f"/api/documents/{document['id']}/chunks").json()["total"] == 0
    assert worker(client, database, embeddings).run_once()
    status = client.get(f"/api/documents/{document['id']}/status").json()
    assert status["status"] == "ready" and status["chunk_count"] > 0
    chunks = client.get(f"/api/documents/{document['id']}/chunks").json()["items"]
    assert chunks[0]["section_heading"] == "Troubleshooting"
    assert "WARNING" in chunks[0]["content"] and "Inspect relay" in chunks[0]["content"]
    duplicate = upload(client, devices=[a["id"], b["id"]]).json()
    assert duplicate["id"] == document["id"] and duplicate["duplicate"]
    assert len(list(client.app.state.settings.storage_dir.iterdir())) == 1
    assert client.get("/api/documents", params={"device_id": b["id"]}).json()["total"] == 1
    updated = client.put(
        f"/api/documents/{document['id']}", json={"device_ids": [a["id"]], "title": "Updated Manual"}
    )
    assert updated.status_code == 200 and updated.json()["device_ids"] == [a["id"]]
    assert client.get("/api/documents", params={"device_id": b["id"]}).json()["total"] == 0
    assert client.delete(f"/api/documents/{document['id']}").status_code == 204
    assert not list(client.app.state.settings.storage_dir.iterdir())
    assert client.get(f"/api/documents/{document['id']}/chunks").status_code == 404


def test_upload_validation_and_empty_corrupt_ingestion(client, database, embeddings):
    assert upload(client, name="bad.exe").status_code == 415
    assert upload(client, devices=[str(uuid4())]).status_code == 404
    assert upload(client, text="").status_code == 422
    assert upload(client, metadata='{"_ingestion":{}}').status_code == 422
    binary = client.post(
        "/api/documents/upload",
        data={"title": "Bad", "document_type": "manual"},
        files={"file": ("bad.txt", b"\x00\xff", "text/plain")},
    )
    assert binary.status_code == 415
    corrupt = client.post(
        "/api/documents/upload",
        data={"title": "Corrupt PDF", "document_type": "manual"},
        files={"file": ("bad.pdf", b"%PDF-1.7\ncorrupt", "application/pdf")},
    )
    assert corrupt.status_code == 202
    assert worker(client, database, embeddings).run_once()
    status = client.get(f"/api/documents/{corrupt.json()['id']}/status").json()
    assert (
        status["status"] == "failed"
        and status["retryable"] is False
        and "extraction failed" in status["error"]
    )
    empty = upload(client, text=" \n\n ").json()
    assert worker(client, database, embeddings).run_once()
    assert client.get(f"/api/documents/{empty['id']}/status").json()["status"] == "failed"


def test_reprocess_atomic_replacement_version_and_crash_recovery(client, database, embeddings):
    document = upload(client).json()
    identifier = document["id"]
    runner = worker(client, database, embeddings)
    runner.run_once()
    first = client.get(f"/api/documents/{identifier}/chunks").json()["items"]
    assert client.post(f"/api/documents/{identifier}/reprocess").status_code == 202
    runner.run_once()
    second = client.get(f"/api/documents/{identifier}/chunks").json()["items"]
    assert len(first) == len(second) and first[0]["chunk_id"] != second[0]["chunk_id"]
    assert client.put(f"/api/documents/{identifier}", json={"version": "2"}).json()["status"] == "uploaded"
    # Simulate a dead worker after claiming: no live advisory lock remains.
    with database.session() as session:
        row = session.get(Document, UUID(identifier))
        row.status = "processing"
    assert runner.run_once()
    assert client.get(f"/api/documents/{identifier}/status").json()["status"] == "ready"
    assert client.get(f"/api/documents/{identifier}/chunks").json()["items"][0]["document_version"] == "2"


def test_extraction_pdf_txt_markdown_and_structure(client, tmp_path):
    settings = client.app.state.settings
    path = tmp_path / "example.pdf"
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(40, 750, "TROUBLESHOOTING")
    pdf.drawString(40, 720, "Clicking during startup may indicate a worn relay.")
    pdf.showPage()
    pdf.drawString(40, 750, "MAINTENANCE")
    pdf.drawString(40, 720, "Inspect cooling fans to prevent overheating.")
    pdf.save()
    path.write_bytes(buffer.getvalue())
    pages = extract(path, settings)
    assert [page for page, _ in pages] == [1, 2]
    sections = structures(pages)
    assert sections[0].heading == "TROUBLESHOOTING" and sections[0].page == 1
    assert sections[-1].page == 2
    for suffix in [".txt", ".md"]:
        text = tmp_path / ("example" + suffix)
        text.write_text("# Manual\n\nRelay inspection", encoding="utf-8")
        assert "Relay" in extract(text, settings)[0][1]
    path.write_bytes(b"bad")
    with pytest.raises(IngestionError):
        extract(path, settings)


def test_long_procedure_bounded_and_document_busy(client, database, embeddings):
    settings = client.app.state.settings
    text = "# SAFETY\nWARNING: Disconnect power.\n\n" + "\n\n".join(
        f"{n}. Check the relay contacts safely." for n in range(100)
    )
    chunks = Chunker(settings, embeddings).split(structures([(1, text)]))
    assert len(chunks) > 1
    assert all(embeddings.token_count(chunk.content) <= embeddings.max_tokens for chunk in chunks)
    assert all(chunk.metadata["protected_procedure"] for chunk in chunks)
    document = upload(client).json()
    with database.document_lock(document["id"]):
        assert client.post(f"/api/documents/{document['id']}/reprocess").status_code == 409
        assert client.delete(f"/api/documents/{document['id']}").status_code == 409


def test_retryable_failure_and_reprocessing_preserves_old_chunks(client, database, embeddings):
    document = upload(client).json()
    runner = worker(client, database, embeddings)
    runner.run_once()
    identifier = document["id"]
    before = client.get(f"/api/documents/{identifier}/chunks").json()["items"]
    client.post(f"/api/documents/{identifier}/reprocess")

    def broken(texts):
        raise RuntimeError("private document contents must not be logged")

    runner.embeddings.texts = broken
    runner.run_once()
    status = client.get(f"/api/documents/{identifier}/status").json()
    assert status["status"] == "failed" and status["retryable"]
    assert "private" not in status["error"]
    assert client.get(f"/api/documents/{identifier}/chunks").json()["items"] == before


def test_worker_does_not_mark_a_live_final_attempt_failed(client, database, embeddings):
    document = upload(client).json()
    identifier = UUID(document["id"])
    runner = worker(client, database, embeddings)
    with database.session() as session:
        row = session.get(Document, identifier)
        row.status = "processing"
        row.metadata_ = {**row.metadata_, "_ingestion": {"attempts": runner.settings.worker_max_attempts}}
    with database.document_lock(identifier):
        assert runner.run_once() is False
        assert client.get(f"/api/documents/{identifier}/status").json()["status"] == "processing"
    assert runner.run_once() is False
    assert client.get(f"/api/documents/{identifier}/status").json()["status"] == "failed"
