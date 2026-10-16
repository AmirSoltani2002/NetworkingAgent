import logging
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, delete, func, or_, select

from .chunking import Chunker, extract, structures
from .documents import DocumentService
from .errors import IngestionError, ServiceError
from .models import Document, DocumentChunk

log = logging.getLogger("rag")


class IngestionWorker:
    def __init__(self, database, settings, embeddings, chunker=None):
        self.db = database
        self.settings = settings
        self.embeddings = embeddings
        self.documents = DocumentService(database, settings)
        self.chunker = chunker or Chunker(settings, embeddings)

    def run_once(self):
        with self.db.session() as session:
            candidates = session.scalars(
                select(Document)
                .where(
                    or_(
                        Document.status.in_(["uploaded", "processing"]),
                        and_(
                            Document.status == "failed",
                            Document.metadata_["_ingestion"]["retryable"].astext == "true",
                        ),
                    )
                )
                .order_by(Document.updated_at, Document.id)
                .limit(100)
            ).all()
            identifiers = []
            now = datetime.now(UTC)
            for document in candidates:
                state = document.metadata_.get("_ingestion", {})
                if document.status == "failed" and not state.get("retryable", False):
                    continue
                if (
                    state.get("attempts", 0) >= self.settings.worker_max_attempts
                    and document.status != "processing"
                ):
                    continue
                due = state.get("next_attempt_at")
                if due and datetime.fromisoformat(due) > now:
                    continue
                identifiers.append(document.id)
        for identifier in identifiers:
            try:
                with self.db.document_lock(identifier):
                    return self.process(identifier)
            except ServiceError as error:
                if error.status != 409:
                    raise
        return False

    def process(self, identifier):
        started = time.monotonic()
        with self.db.session() as session:
            document = session.get(Document, identifier)
            if document is None or document.status == "ready":
                return False
            state = document.metadata_.get("_ingestion", {})
            if state.get("attempts", 0) >= self.settings.worker_max_attempts:
                if document.status == "processing":
                    document.status = "failed"
                    document.metadata_ = {
                        **document.metadata_,
                        "_ingestion": {
                            **state,
                            "retryable": False,
                            "error": "Processing was interrupted too many times; request reprocessing",
                        },
                    }
                return False
            if document.status == "failed" and not state.get("retryable", False):
                return False
            state = {
                **state,
                "attempts": state.get("attempts", 0) + 1,
                "error": None,
                "retryable": False,
                "started_at": datetime.now(UTC).isoformat(),
            }
            document.metadata_ = {**document.metadata_, "_ingestion": state}
            document.status = "processing"
            document.updated_at = func.now()
            relative = document.file_path
            version = document.version
        try:
            pages = extract(self.documents.safe_path(relative), self.settings)
            chunks = self.chunker.split(structures(pages))
            vectors = self.embeddings.texts([chunk.content for chunk in chunks])
            if len(vectors) != len(chunks) or any(
                len(vector) != self.settings.embedding_dimension for vector in vectors
            ):
                raise IngestionError("Embedding dimensions do not match the configured model")
            with self.db.session() as session:
                document = session.get(Document, identifier)
                if document is None:
                    return False
                # Replacement and ready state commit together; old explicit links cascade away.
                session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == identifier))
                for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
                    session.add(
                        DocumentChunk(
                            id=uuid4(),
                            document_id=identifier,
                            content=chunk.content,
                            embedding=vector,
                            section_heading=chunk.heading,
                            section_path=chunk.path,
                            page_number=chunk.page,
                            chunk_index=index,
                            metadata_={
                                **chunk.metadata,
                                "embedding": self.settings.embedding_contract,
                                "document_version": version,
                            },
                        )
                    )
                duration = round((time.monotonic() - started) * 1000, 2)
                document.status = "ready"
                document.updated_at = func.now()
                document.metadata_ = {
                    **document.metadata_,
                    "_ingestion": {
                        **state,
                        "duration_ms": duration,
                        "completed_at": datetime.now(UTC).isoformat(),
                        "embedding": self.settings.embedding_contract,
                        "error": None,
                        "next_attempt_at": None,
                    },
                }
            log.info(
                "document_ready",
                extra={
                    "event": "document_ready",
                    "document_id": str(identifier),
                    "chunk_count": len(chunks),
                    "duration_ms": duration,
                },
            )
        except Exception as error:
            retryable = not isinstance(error, IngestionError)
            message = (
                str(error)
                if isinstance(error, IngestionError)
                else "Document processing failed; retry or inspect the error-type log"
            )
            attempts = state["attempts"]
            retryable = retryable and attempts < self.settings.worker_max_attempts
            with self.db.session() as session:
                document = session.get(Document, identifier)
                if document:
                    document.status = "failed"
                    document.updated_at = func.now()
                    document.metadata_ = {
                        **document.metadata_,
                        "_ingestion": {
                            **state,
                            "error": message,
                            "retryable": retryable,
                            "duration_ms": round((time.monotonic() - started) * 1000, 2),
                            "next_attempt_at": (
                                datetime.now(UTC)
                                + timedelta(seconds=self.settings.worker_retry_seconds * 2 ** (attempts - 1))
                            ).isoformat()
                            if retryable
                            else None,
                        },
                    }
            log.error(
                "document_failed",
                extra={
                    "event": "document_failed",
                    "document_id": str(identifier),
                    "attempt": attempts,
                    "retryable": retryable,
                    "error_type": type(error).__name__,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                },
            )
        return True
