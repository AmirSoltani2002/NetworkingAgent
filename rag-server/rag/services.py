from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from .errors import ServiceError
from .models import Device, DeviceDocument, Document, DocumentChunk, Issue, IssueEvidence


def require(session, model, identifier, lock=False):
    row = session.get(model, identifier, with_for_update=lock)
    if row is None:
        raise ServiceError(404, "NOT_FOUND", f"{model.__tablename__} record not found")
    return row


def device_json(row):
    return {
        "id": str(row.id),
        "name": row.name,
        "model": row.model,
        "manufacturer": row.manufacturer,
        "description": row.description,
        "metadata": row.metadata_,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def issue_json(row):
    return {
        "id": str(row.id),
        "device_id": str(row.device_id),
        "title": row.title,
        "category": row.category,
        "symptoms": row.symptoms,
        "possible_cause": row.possible_cause,
        "possible_cause_confirmed": False,
        "description": row.description,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def chunk_json(chunk, document):
    return {
        "chunk_id": str(chunk.id),
        "document_id": str(document.id),
        "document_title": document.title,
        "document_version": document.version,
        "content": chunk.content,
        "section_heading": chunk.section_heading,
        "section_path": chunk.section_path,
        "page_number": chunk.page_number,
        "chunk_index": chunk.chunk_index,
        "metadata": chunk.metadata_,
    }


def page(session, statement, serialize, offset, limit):
    total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    items = session.scalars(statement.offset(offset).limit(limit)).all()
    return {"items": [serialize(row) for row in items], "total": total, "offset": offset, "limit": limit}


def escaped_contains(value):
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class KnowledgeService:
    def __init__(self, database, embeddings):
        self.db = database
        self.embeddings = embeddings

    def list_devices(self, offset=0, limit=20, name=None, model=None, manufacturer=None):
        statement = select(Device).order_by(Device.created_at, Device.id)
        if name:
            statement = statement.where(Device.name.ilike(escaped_contains(name), escape="\\"))
        if model:
            statement = statement.where(func.lower(Device.model) == model.lower())
        if manufacturer:
            statement = statement.where(func.lower(Device.manufacturer) == manufacturer.lower())
        with self.db.session() as session:
            return page(session, statement, device_json, offset, limit)

    def find_device(self, name, model=None):
        with self.db.session() as session:
            statement = select(Device).where(func.lower(Device.name) == name.strip().lower())
            if model:
                statement = statement.where(func.lower(Device.model) == model.strip().lower())
            rows = session.scalars(statement.order_by(Device.id).limit(101)).all()
            return {
                "matches": [device_json(row) for row in rows[:100]],
                "ambiguous": len(rows) > 1,
                "truncated": len(rows) > 100,
            }

    def get_device(self, identifier):
        with self.db.session() as session:
            return device_json(require(session, Device, identifier))

    def save_device(self, data, identifier=None):
        values = data.model_dump()
        values["metadata_"] = values.pop("metadata")
        try:
            with self.db.session() as session:
                row = require(session, Device, identifier) if identifier else Device()
                for key, value in values.items():
                    setattr(row, key, value)
                session.add(row)
                session.flush()
                return device_json(row)
        except IntegrityError:
            raise ServiceError(
                409, "DUPLICATE_DEVICE", "A device with this name, model, and manufacturer already exists"
            ) from None

    def delete_device(self, identifier):
        with self.db.session() as session:
            session.delete(require(session, Device, identifier))

    def list_issues(self, offset=0, limit=20, device_id=None, category=None, symptoms=None):
        statement = select(Issue).order_by(Issue.created_at, Issue.id)
        if device_id:
            statement = statement.where(Issue.device_id == device_id)
        if category:
            statement = statement.where(func.lower(Issue.category) == category.lower())
        if symptoms:
            statement = statement.where(Issue.symptoms.ilike(escaped_contains(symptoms), escape="\\"))
        with self.db.session() as session:
            if device_id:
                require(session, Device, device_id)
            return page(session, statement, issue_json, offset, limit)

    def get_issue(self, identifier):
        with self.db.session() as session:
            return issue_json(require(session, Issue, identifier))

    def save_issue(self, data, identifier=None):
        values = data.model_dump()
        searchable = ["title", "category", "symptoms", "possible_cause", "description"]
        try:
            with self.db.session() as session:
                require(session, Device, values["device_id"])
                row = require(session, Issue, identifier, lock=True) if identifier else Issue()
                if identifier and row.device_id != values["device_id"]:
                    # Serialize applicability changes with document updates and evidence insertion.
                    linked_documents = (
                        select(DocumentChunk.document_id)
                        .join(IssueEvidence)
                        .where(IssueEvidence.issue_id == identifier)
                    )
                    session.scalars(
                        select(Document)
                        .where(Document.id.in_(linked_documents))
                        .order_by(Document.id)
                        .with_for_update()
                    ).all()
                    applicable = select(DeviceDocument.document_id).where(
                        DeviceDocument.device_id == values["device_id"]
                    )
                    session.execute(
                        delete(IssueEvidence).where(
                            IssueEvidence.issue_id == identifier,
                            IssueEvidence.chunk_id.in_(
                                select(DocumentChunk.id).where(DocumentChunk.document_id.not_in(applicable))
                            ),
                        )
                    )
                changed = not identifier or any(getattr(row, key) != values[key] for key in searchable)
                if changed:
                    source = "\n".join(f"{key}: {values[key]}" for key in searchable)
                    row.embedding = self.embeddings.texts([source])[0]
                for key, value in values.items():
                    setattr(row, key, value)
                session.add(row)
                session.flush()
                return issue_json(row)
        except IntegrityError:
            raise ServiceError(
                409,
                "ISSUE_CONFLICT",
                "Issue title already exists for this device or a referenced device changed",
            ) from None

    def delete_issue(self, identifier):
        with self.db.session() as session:
            session.delete(require(session, Issue, identifier))

    def evidence(self, issue_id):
        with self.db.session() as session:
            require(session, Issue, issue_id)
            rows = session.execute(
                select(IssueEvidence, DocumentChunk, Document)
                .join(DocumentChunk, DocumentChunk.id == IssueEvidence.chunk_id)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(IssueEvidence.issue_id == issue_id)
                .order_by(DocumentChunk.id)
            ).all()
            return {
                "issue_id": str(issue_id),
                "items": [
                    dict(chunk_json(chunk, doc), evidence_type=link.evidence_type, document_status=doc.status)
                    for link, chunk, doc in rows
                ],
            }

    def link_evidence(self, issue_id, data):
        with self.db.session() as session:
            issue = require(session, Issue, issue_id, lock=True)
            chunk = require(session, DocumentChunk, data.chunk_id)
            document = require(session, Document, chunk.document_id, lock=True)
            if document.status != "ready":
                raise ServiceError(409, "DOCUMENT_NOT_READY", "Evidence must reference a ready document")
            if session.get(DeviceDocument, (issue.device_id, document.id)) is None:
                raise ServiceError(
                    422, "EVIDENCE_DEVICE_MISMATCH", "Associate the document with the issue's device first"
                )
            link = session.get(IssueEvidence, (issue_id, data.chunk_id))
            if link is None:
                link = IssueEvidence(issue_id=issue_id, chunk_id=data.chunk_id)
            link.evidence_type = data.evidence_type
            session.add(link)
            session.flush()
            return {
                "issue_id": str(issue_id),
                "chunk_id": str(data.chunk_id),
                "evidence_type": link.evidence_type,
            }

    def unlink_evidence(self, issue_id, chunk_id):
        with self.db.session() as session:
            require(session, Issue, issue_id)
            link = session.get(IssueEvidence, (issue_id, chunk_id))
            if link is None:
                raise ServiceError(404, "NOT_FOUND", "Evidence link not found")
            session.delete(link)

    def context(self, chunk_ids):
        identifiers = list(dict.fromkeys(UUID(str(value)) for value in chunk_ids))
        if not identifiers or len(identifiers) > 100:
            raise ServiceError(422, "INVALID_CHUNKS", "Provide between 1 and 100 chunk IDs")
        with self.db.session() as session:
            rows = session.execute(
                select(DocumentChunk, Document)
                .join(Document)
                .where(DocumentChunk.id.in_(identifiers), Document.status == "ready")
            ).all()
            by_id = {chunk.id: chunk_json(chunk, document) for chunk, document in rows}
            return {
                "items": [by_id[item] for item in identifiers if item in by_id],
                "missing_chunk_ids": [str(item) for item in identifiers if item not in by_id],
            }
