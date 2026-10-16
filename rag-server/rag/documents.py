import codecs
import hashlib
import os
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from .errors import ServiceError
from .models import Device, DeviceDocument, Document, DocumentChunk, Issue, IssueEvidence
from .services import chunk_json, page, require


def document_json(session, document):
    device_ids = session.scalars(
        select(DeviceDocument.device_id)
        .where(DeviceDocument.document_id == document.id)
        .order_by(DeviceDocument.device_id)
    ).all()
    return {
        "id": str(document.id),
        "title": document.title,
        "document_type": document.document_type,
        "file_path": document.file_path,
        "version": document.version,
        "status": document.status,
        "metadata": {key: value for key, value in document.metadata_.items() if not key.startswith("_")},
        "device_ids": [str(identifier) for identifier in device_ids],
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
    }


class DocumentService:
    def __init__(self, database, settings):
        self.db = database
        self.settings = settings
        self.root = settings.storage_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def safe_path(self, relative):
        path = (self.root / relative).resolve()
        if path.parent != self.root or path.name != relative:
            raise ServiceError(500, "UNSAFE_STORED_PATH", "Stored file path is invalid")
        return path

    def validate_devices(self, session, identifiers):
        unique = set(identifiers)
        found = (
            set(session.scalars(select(Device.id).where(Device.id.in_(unique))).all()) if unique else set()
        )
        if unique != found:
            raise ServiceError(404, "DEVICE_NOT_FOUND", "One or more referenced devices do not exist")
        return unique

    def associations(self, session, document_id, identifiers, replace=False):
        unique = self.validate_devices(session, identifiers)
        if replace:
            session.execute(
                delete(IssueEvidence).where(
                    IssueEvidence.chunk_id.in_(
                        select(DocumentChunk.id).where(DocumentChunk.document_id == document_id)
                    ),
                    IssueEvidence.issue_id.in_(select(Issue.id).where(Issue.device_id.not_in(unique))),
                )
            )
            session.execute(delete(DeviceDocument).where(DeviceDocument.document_id == document_id))
        for identifier in unique:
            if session.get(DeviceDocument, (identifier, document_id)) is None:
                session.add(DeviceDocument(device_id=identifier, document_id=document_id))
        session.flush()

    async def upload(self, upload, data):
        suffix = Path((upload.filename or "").replace("\\", "/")).suffix.lower()
        if suffix not in {".pdf", ".txt", ".md", ".markdown"}:
            raise ServiceError(415, "UNSUPPORTED_FILE", "Upload a PDF, UTF-8 TXT, or Markdown file")
        accepted = {
            ".pdf": {"application/pdf", "application/octet-stream"},
            ".txt": {"text/plain", "application/octet-stream"},
            ".md": {"text/plain", "text/markdown", "text/x-markdown", "application/octet-stream"},
            ".markdown": {"text/plain", "text/markdown", "application/octet-stream"},
        }
        if upload.content_type not in accepted[suffix]:
            raise ServiceError(415, "UNSUPPORTED_MEDIA", "File extension and content type do not match")
        # Validate relationships before storing any bytes.
        with self.db.session() as session:
            self.validate_devices(session, data.device_ids)
        identifier = uuid4()
        relative = f"{identifier}{suffix}"
        path = self.safe_path(relative)
        digest = hashlib.sha256()
        size = 0
        first = b""
        decoder = codecs.getincrementaldecoder("utf-8-sig")() if suffix != ".pdf" else None
        committed = False
        created = False
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            created = True
            with os.fdopen(descriptor, "wb") as original:
                while block := await upload.read(1024 * 1024):
                    size += len(block)
                    if size > self.settings.max_upload_mb * 1024 * 1024:
                        raise ServiceError(413, "FILE_TOO_LARGE", "File exceeds the configured upload limit")
                    first = (first + block)[:1024]
                    if decoder:
                        if b"\x00" in block:
                            raise ServiceError(
                                415, "BINARY_TEXT", "Text documents must be UTF-8 without NUL bytes"
                            )
                        try:
                            decoder.decode(block)
                        except UnicodeError:
                            raise ServiceError(
                                415, "INVALID_ENCODING", "Text documents must use UTF-8 encoding"
                            ) from None
                    digest.update(block)
                    original.write(block)
                if decoder:
                    try:
                        decoder.decode(b"", final=True)
                    except UnicodeError:
                        raise ServiceError(
                            415, "INVALID_ENCODING", "Text documents must use UTF-8 encoding"
                        ) from None
                original.flush()
                os.fsync(original.fileno())
            if not size:
                raise ServiceError(422, "EMPTY_FILE", "The uploaded file is empty")
            if suffix == ".pdf" and not first.startswith(b"%PDF-"):
                raise ServiceError(415, "INVALID_PDF", "The file does not have a PDF header")
            checksum = digest.hexdigest()
            statement = select(Document).where(
                Document.metadata_["_source"]["sha256"].astext == checksum,
                func.lower(Document.title) == data.title.lower(),
                func.lower(Document.document_type) == data.document_type.lower(),
                Document.version == data.version,
            )
            try:
                with self.db.session() as session:
                    document = session.scalar(statement.with_for_update())
                    duplicate = document is not None
                    if document is None:
                        document = Document(
                            id=identifier,
                            title=data.title,
                            document_type=data.document_type,
                            version=data.version,
                            file_path=relative,
                            status="uploaded",
                            metadata_={
                                **data.metadata,
                                "_source": {
                                    "sha256": checksum,
                                    "size": size,
                                    "filename": Path((upload.filename or "file").replace("\\", "/")).name[
                                        :255
                                    ],
                                },
                                "_ingestion": {"attempts": 0},
                            },
                        )
                        session.add(document)
                        session.flush()
                    self.associations(session, document.id, data.device_ids)
                    result = document_json(session, document)
                    result["duplicate"] = duplicate
                committed = not duplicate
                return result
            except IntegrityError:
                # Concurrent identical uploads: return the winner, merging device associations.
                with self.db.session() as session:
                    document = session.scalar(statement.with_for_update())
                    if document is None:
                        raise ServiceError(
                            409, "UPLOAD_CONFLICT", "Document identity or device references changed"
                        ) from None
                    self.associations(session, document.id, data.device_ids)
                    return dict(document_json(session, document), duplicate=True)
        finally:
            await upload.close()
            if created and not committed:
                path.unlink(missing_ok=True)

    def list(self, offset=0, limit=20, device_id=None, document_type=None, status=None):
        statement = select(Document).order_by(Document.created_at, Document.id)
        if device_id:
            statement = statement.where(
                Document.id.in_(
                    select(DeviceDocument.document_id).where(DeviceDocument.device_id == device_id)
                )
            )
        if document_type:
            statement = statement.where(func.lower(Document.document_type) == document_type.lower())
        if status:
            statement = statement.where(Document.status == status)
        with self.db.session() as session:
            if device_id:
                require(session, Device, device_id)
            return page(session, statement, lambda row: document_json(session, row), offset, limit)

    def get(self, identifier):
        with self.db.session() as session:
            return document_json(session, require(session, Document, identifier))

    def status(self, identifier):
        with self.db.session() as session:
            document = require(session, Document, identifier)
            job = document.metadata_.get("_ingestion", {})
            count = session.scalar(
                select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == identifier)
            )
            return {
                "id": str(identifier),
                "status": document.status,
                "chunk_count": count,
                "attempts": job.get("attempts", 0),
                "error": job.get("error"),
                "retryable": job.get("retryable", False),
                "next_attempt_at": job.get("next_attempt_at"),
                "duration_ms": job.get("duration_ms"),
                "embedding": job.get("embedding"),
            }

    def chunks(self, identifier, offset=0, limit=20):
        with self.db.session() as session:
            document = require(session, Document, identifier)
            return page(
                session,
                select(DocumentChunk)
                .where(DocumentChunk.document_id == identifier)
                .order_by(DocumentChunk.chunk_index),
                lambda chunk: chunk_json(chunk, document),
                offset,
                limit,
            )

    def update(self, identifier, data):
        with self.db.document_lock(identifier), self.db.session() as session:
            document = require(session, Document, identifier, lock=True)
            values = data.model_dump(exclude_unset=True)
            if "device_ids" in values:
                self.associations(session, identifier, values.pop("device_ids"), replace=True)
            if "metadata" in values:
                private = {key: value for key, value in document.metadata_.items() if key.startswith("_")}
                document.metadata_ = {**values.pop("metadata"), **private}
            if "version" in values and values["version"] != document.version:
                document.status = "uploaded"
                document.metadata_ = {**document.metadata_, "_ingestion": {"attempts": 0}}
            for key, value in values.items():
                setattr(document, key, value)
            document.updated_at = func.now()
            session.flush()
            return document_json(session, document)

    def reprocess(self, identifier):
        with self.db.document_lock(identifier), self.db.session() as session:
            document = require(session, Document, identifier)
            document.status = "uploaded"
            document.metadata_ = {**document.metadata_, "_ingestion": {"attempts": 0}}
            document.updated_at = func.now()
            session.flush()
            return document_json(session, document)

    def delete(self, identifier):
        with self.db.document_lock(identifier):
            quarantine = None
            path = None
            try:
                with self.db.session() as session:
                    document = require(session, Document, identifier)
                    path = self.safe_path(document.file_path)
                    if path.exists():
                        quarantine = self.root / f".deleting-{identifier}-{uuid4()}"
                        path.rename(quarantine)
                        os.utime(quarantine, None)
                    session.delete(document)
                if quarantine:
                    quarantine.unlink(missing_ok=True)
            except Exception:
                if quarantine and quarantine.exists() and path is not None:
                    quarantine.rename(path)
                raise

    def sweep_orphans(self, minimum_age_seconds=3600):
        # Recover file/DB crash boundaries. Never race a fresh upload or delete.
        with self.db.session() as session:
            referenced = set(session.scalars(select(Document.file_path)).all())
        cutoff = time.time() - minimum_age_seconds
        for path in self.root.iterdir():
            if not path.is_file() or path.stat().st_mtime > cutoff:
                continue
            if path.name.startswith(".deleting-"):
                parts = path.name.split("-")
                original_id = "-".join(parts[1:6])
                original = next((name for name in referenced if name.startswith(original_id + ".")), None)
                if original and not (self.root / original).exists():
                    path.rename(self.root / original)
                    continue
            if path.name not in referenced:
                path.unlink(missing_ok=True)
