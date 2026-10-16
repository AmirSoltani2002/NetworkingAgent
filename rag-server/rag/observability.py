import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_context = ContextVar("rag_request_id", default=None)
FIELDS = {
    "request_id",
    "method",
    "status",
    "duration_ms",
    "document_id",
    "chunk_count",
    "error_type",
    "attempt",
    "retryable",
    "device_id",
    "issue_category",
    "document_type",
    "document_ids_filter",
    "top_k",
    "strategy",
    "reranked",
    "retrieved_document_ids",
    "retrieved_chunk_ids",
}


class JsonFormatter(logging.Formatter):
    def format(self, record):
        value = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", "library_log"),
        }
        # Third-party messages/tracebacks may contain provider input or headers: do not serialize them.
        for field in FIELDS:
            if hasattr(record, field):
                value[field] = getattr(record, field)
        if not value.get("request_id") and request_id_context.get():
            value["request_id"] = request_id_context.get()
        return json.dumps(value, default=str)


def configure_logging(level):
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), handlers=[handler], force=True)
