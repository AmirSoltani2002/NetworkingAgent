import asyncio
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Query
from typing import Annotated
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .dataset import DatasetService
from .db import database
from .errors import ServiceError
from .mcp_server import build_mcp
from .model import ModelService
from .schemas import BatchInput, DatasetFilters, Features, Prediction, TrainInput
from .seed import initialize

logger = logging.getLogger("manufacturing")


class Protection:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        if scope["path"] not in ["/health", "/ready"]:
            expected = f"Bearer {self.settings.api_key.get_secret_value()}".encode()
            if not hmac.compare_digest(headers.get(b"authorization", b""), expected):
                return await JSONResponse({"code": "UNAUTHORIZED", "message": "Provide a valid bearer token"}, status_code=401)(scope, receive, send)
        request_id = str(uuid4())
        started = time.monotonic()
        total = 0
        status = 500

        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > 1024 * 1024:
                raise ServiceError("REQUEST_TOO_LARGE", "Request body exceeds 1 MiB", 413)
            return message

        async def response_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)
        try:
            async with asyncio.timeout(self.settings.request_timeout):
                await self.app(scope, bounded_receive, response_send)
        except TimeoutError:
            if status == 500:
                await JSONResponse({"code": "TIMEOUT", "message": "Operation timed out; narrow filters or check service status"}, status_code=504)(scope, receive, send)
        finally:
            logger.info(json.dumps({"event": "request", "request_id": request_id, "method": scope["method"],
                "path": scope["path"] if scope["path"].startswith("/api/") else "/mcp" if scope["path"].startswith("/mcp") else scope["path"],
                "status": status, "duration_ms": int((time.monotonic()-started)*1000)}))


def create_app(settings=None):
    settings = settings or Settings()
    engine, sessions = database(settings)
    model = ModelService(engine, sessions, settings)

    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(initialize, engine, sessions, settings)
        model.start()
        async with mcp.session_manager.run():
            yield
        await run_in_threadpool(model.stop)
        engine.dispose()

    app = FastAPI(title="Synthetic Manufacturing Quality", version="1.0", lifespan=lifespan)
    app.state.model = model
    app.state.dataset = DatasetService(sessions, model, settings)
    app.state.engine, app.state.sessions = engine, sessions
    mcp = build_mcp(app, settings)
    mcp_app = mcp.streamable_http_app()
    app.add_middleware(Protection, settings=settings)

    @app.exception_handler(ServiceError)
    async def service_error(_request, error):
        return JSONResponse({"code": error.code, "message": error.message}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, error):
        # Validation details omit submitted values and credentials.
        fields = [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in error.errors()]
        return JSONResponse({"code": "INVALID_INPUT", "message": "Check required fields and feature bounds", "fields": fields}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(_request, _error):
        logger.error(json.dumps({"event": "service_error"}))
        return JSONResponse({"code": "SERVICE_ERROR", "message": "Operation failed; check service health"}, status_code=500)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "manufacturing-ml"}

    @app.get("/ready")
    def ready():
        try:
            with engine.connect() as connection:
                count = connection.scalar(text("SELECT count(*) FROM manufacturing_products"))
            if not count or not model._thread or not model._thread.is_alive():
                raise ValueError()
            return {"status": "ready", "record_count": count, "model_status": model.status()["status"]}
        except Exception:
            raise ServiceError("NOT_READY", "Database, training worker or artifact storage is unavailable", 503) from None

    @app.post("/api/model/train", status_code=202)
    def train(request: TrainInput):
        return model.submit(request)

    @app.get("/api/model/status")
    def status(job_id: str | None = None):
        return model.job(job_id) if job_id else model.status()

    @app.get("/api/model/metrics")
    def metrics():
        return model.metrics()

    @app.post("/api/model/evaluate")
    def evaluate():
        return model.evaluate_model()

    @app.post("/api/model/predict", response_model=Prediction)
    def predict(features: Features):
        return model.predict([features.model_dump()])[0]

    @app.post("/api/model/predict-batch", response_model=list[Prediction])
    def batch(request: BatchInput):
        return model.predict([r.model_dump() for r in request.records])

    @app.get("/api/dataset")
    def dataset(filters: Annotated[DatasetFilters, Query()]):
        return app.state.dataset.records(filters)

    @app.get("/api/dataset/predictions")
    def predictions(filters: Annotated[DatasetFilters, Query()]):
        return app.state.dataset.predictions(filters)

    @app.get("/api/dataset/statistics")
    def statistics():
        return app.state.dataset.statistics()

    app.mount("/", mcp_app)
    return app
