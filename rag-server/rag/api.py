import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .config import Settings
from .db import Database
from .documents import DocumentService
from .errors import ServiceError
from .mcp_server import build_mcp
from .middleware import BodyLimitMiddleware, RequestTooLarge
from .observability import request_id_context
from .retrieval import RetrievalService
from .schemas import DeviceInput, DocumentUpdate, DocumentUpload, EvidenceInput, IssueInput, SearchInput
from .services import KnowledgeService

log = logging.getLogger("rag")


def create_app(settings=None, embeddings=None, database=None):
    settings = settings or Settings()
    db = database or Database(settings)
    supplied_embeddings = embeddings

    @asynccontextmanager
    async def lifespan(app):
        db.check_contract()
        if supplied_embeddings is None:
            from .embeddings import LocalEmbeddings

            app.state.embeddings = LocalEmbeddings(settings)
        else:
            app.state.embeddings = supplied_embeddings
        app.state.knowledge = KnowledgeService(db, app.state.embeddings)
        app.state.db = db
        app.state.settings = settings
        app.state.documents = DocumentService(db, settings)
        reranker = None
        if settings.reranker_enabled:
            from .embeddings import LocalReranker

            reranker = LocalReranker(settings)
        app.state.retrieval = RetrievalService(db, settings, app.state.embeddings, reranker)
        async with app.state.mcp.session_manager.run():
            yield
        if database is None:
            db.engine.dispose()

    app = FastAPI(
        title="Local RAG Evidence Retrieval",
        version="0.1.0",
        lifespan=lifespan,
        description="Retrieval only. Possible causes are hypotheses; scores are not confidence probabilities.",
    )

    def openapi():
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            if settings.auth_required:
                schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
                    "type": "http",
                    "scheme": "bearer",
                }
                for path, methods in schema["paths"].items():
                    if path.startswith("/api/"):
                        for operation in methods.values():
                            operation["security"] = [{"BearerAuth": []}]
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi
    app.add_middleware(BodyLimitMiddleware, limit=settings.max_upload_mb * 1024 * 1024 + 65536)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = str(uuid4())
        request.state.request_id = request_id
        context_token = request_id_context.set(request_id)
        started = time.monotonic()
        if (
            request.url.path
            not in {"/health", "/ready", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
            and settings.auth_required
        ):
            authorization = request.headers.get("authorization", "")
            token = authorization[7:] if authorization.startswith("Bearer ") else ""
            if not secrets.compare_digest(token.encode(), settings.api_key.get_secret_value().encode()):
                request_id_context.reset(context_token)
                return JSONResponse(
                    {
                        "error": {"code": "UNAUTHORIZED", "message": "Valid bearer authentication required"},
                        "request_id": request_id,
                    },
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer", "X-Request-ID": request_id},
                )
        try:
            response = await call_next(request)
        finally:
            request_id_context.reset(context_token)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        log.info(
            "http_request",
            extra={
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            },
        )
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request, error):
        return JSONResponse(
            {
                "error": {"code": error.code, "message": error.message, "details": error.details},
                "request_id": request.state.request_id,
            },
            status_code=error.status,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Pydantic's input/context can contain sensitive fields: return locations only.
        return JSONResponse(
            {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid request data",
                    "fields": [list(item["loc"]) for item in error.errors()],
                },
                "request_id": request.state.request_id,
            },
            status_code=422,
        )

    @app.exception_handler(RequestTooLarge)
    async def oversized(request, error):
        return JSONResponse(
            {
                "error": {"code": "BODY_TOO_LARGE", "message": "Request exceeds the upload limit"},
                "request_id": request.state.request_id,
            },
            status_code=413,
        )

    @app.exception_handler(IntegrityError)
    async def conflict(request, error):
        return JSONResponse(
            {
                "error": {"code": "CONFLICT", "message": "Record conflicts with existing or changed data"},
                "request_id": request.state.request_id,
            },
            status_code=409,
        )

    @app.exception_handler(Exception)
    async def unexpected(request, error):
        log.error(
            "request_failed",
            extra={
                "event": "request_failed",
                "request_id": request.state.request_id,
                "error_type": type(error).__name__,
            },
        )
        return JSONResponse(
            {
                "error": {"code": "INTERNAL_ERROR", "message": "Could not complete the request"},
                "request_id": request.state.request_id,
            },
            status_code=500,
        )

    @app.get("/health")
    def health():
        return {"status": "alive"}

    @app.post("/api/retrieval/search")
    def search_knowledge(data: SearchInput, request: Request):
        return app.state.retrieval.search(data, request.state.request_id)

    @app.get("/ready")
    def ready():
        try:
            with db.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            db.check_contract()
            if not hasattr(app.state, "embeddings"):
                raise RuntimeError()
            return {"status": "ready", "embedding": settings.embedding_contract}
        except Exception:
            return JSONResponse({"status": "not_ready"}, status_code=503)

    @app.get("/api/devices")
    def devices(
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        name: str | None = Query(None, max_length=200),
        model: str | None = Query(None, max_length=200),
        manufacturer: str | None = Query(None, max_length=200),
    ):
        return app.state.knowledge.list_devices(offset, limit, name, model, manufacturer)

    @app.post("/api/documents/upload", status_code=202)
    async def upload_document(
        file: UploadFile = File(),
        title: str = Form(max_length=300),
        document_type: str = Form(max_length=100),
        version: str = Form("1", max_length=100),
        device_ids: str = Form("[]", max_length=10000),
        metadata: str = Form("{}", max_length=16384),
    ):
        try:
            data = DocumentUpload(
                title=title,
                document_type=document_type,
                version=version,
                device_ids=json.loads(device_ids),
                metadata=json.loads(metadata),
            )
        except (ValidationError, ValueError):
            await file.close()
            raise ServiceError(
                422,
                "INVALID_UPLOAD_METADATA",
                "Invalid title/type/version, metadata object, or device-ID array",
            ) from None
        return await app.state.documents.upload(file, data)

    @app.get("/api/documents")
    def documents(
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        device_id: UUID | None = None,
        document_type: str | None = Query(None, max_length=100),
        status: Literal["uploaded", "processing", "ready", "failed"] | None = None,
    ):
        return app.state.documents.list(offset, limit, device_id, document_type, status)

    @app.get("/api/documents/{identifier}")
    def get_document(identifier: UUID):
        return app.state.documents.get(identifier)

    @app.put("/api/documents/{identifier}")
    def update_document(identifier: UUID, data: DocumentUpdate):
        return app.state.documents.update(identifier, data)

    @app.delete("/api/documents/{identifier}", status_code=204)
    def delete_document(identifier: UUID):
        app.state.documents.delete(identifier)
        return Response(status_code=204)

    @app.get("/api/documents/{identifier}/status")
    def document_status(identifier: UUID):
        return app.state.documents.status(identifier)

    @app.get("/api/documents/{identifier}/chunks")
    def document_chunks(identifier: UUID, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
        return app.state.documents.chunks(identifier, offset, limit)

    @app.post("/api/documents/{identifier}/reprocess", status_code=202)
    def reprocess_document(identifier: UUID):
        return app.state.documents.reprocess(identifier)

    @app.post("/api/devices", status_code=201)
    def create_device(data: DeviceInput):
        return app.state.knowledge.save_device(data)

    @app.get("/api/devices/{identifier}")
    def get_device(identifier: UUID):
        return app.state.knowledge.get_device(identifier)

    @app.put("/api/devices/{identifier}")
    def update_device(identifier: UUID, data: DeviceInput):
        return app.state.knowledge.save_device(data, identifier)

    @app.delete("/api/devices/{identifier}", status_code=204)
    def delete_device(identifier: UUID):
        app.state.knowledge.delete_device(identifier)
        return Response(status_code=204)

    @app.get("/api/issues")
    def issues(
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        device_id: UUID | None = None,
        category: str | None = Query(None, max_length=100),
        symptoms: str | None = Query(None, max_length=20000),
    ):
        return app.state.knowledge.list_issues(offset, limit, device_id, category, symptoms)

    @app.post("/api/issues", status_code=201)
    def create_issue(data: IssueInput):
        return app.state.knowledge.save_issue(data)

    @app.get("/api/issues/{identifier}")
    def get_issue(identifier: UUID):
        return app.state.knowledge.get_issue(identifier)

    @app.put("/api/issues/{identifier}")
    def update_issue(identifier: UUID, data: IssueInput):
        return app.state.knowledge.save_issue(data, identifier)

    @app.delete("/api/issues/{identifier}", status_code=204)
    def delete_issue(identifier: UUID):
        app.state.knowledge.delete_issue(identifier)
        return Response(status_code=204)

    @app.get("/api/issues/{identifier}/evidence")
    def get_evidence(identifier: UUID):
        return app.state.knowledge.evidence(identifier)

    @app.post("/api/issues/{identifier}/evidence", status_code=201)
    def link_evidence(identifier: UUID, data: EvidenceInput):
        return app.state.knowledge.link_evidence(identifier, data)

    @app.delete("/api/issues/{identifier}/evidence/{chunk_id}", status_code=204)
    def delete_evidence(identifier: UUID, chunk_id: UUID):
        app.state.knowledge.unlink_evidence(identifier, chunk_id)
        return Response(status_code=204)

    app.state.mcp = build_mcp(app, settings)
    # The MCP child owns /mcp; existing FastAPI routes retain priority over this final mount.
    app.mount("/", app.state.mcp.streamable_http_app())
    return app
