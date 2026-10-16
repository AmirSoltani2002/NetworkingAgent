from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import Settings

# Import-time configuration determines vector types; it must match Alembic's recorded contract.
DIMENSION = Settings().embedding_dimension


class Base(DeclarativeBase):
    pass


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Device(Timestamps, Base):
    __tablename__ = "devices"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    model: Mapped[str] = mapped_column(String(200))
    manufacturer: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default="{}")
    __table_args__ = (
        Index("devices_identity", func.lower(name), func.lower(model), func.lower(manufacturer), unique=True),
        Index("devices_model", "model"),
        Index("devices_manufacturer", "manufacturer"),
    )


class Issue(Timestamps, Base):
    __tablename__ = "issues"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(100))
    symptoms: Mapped[str] = mapped_column(Text)
    possible_cause: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSION))
    __table_args__ = (
        UniqueConstraint("device_id", "title", name="issues_device_title"),
        Index("issues_category", "category"),
    )


class Document(Timestamps, Base):
    __tablename__ = "documents"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(300))
    document_type: Mapped[str] = mapped_column(String(100))
    file_path: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(100), default="1")
    status: Mapped[str] = mapped_column(String(20), default="uploaded", index=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded','processing','ready','failed')", name="documents_status_valid"
        ),
        Index("documents_type", "document_type"),
    )


class DeviceDocument(Base):
    __tablename__ = "device_documents"
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    __table_args__ = (Index("device_documents_document", "document_id"),)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSION))
    section_heading: Mapped[str | None] = mapped_column(Text)
    section_path: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    chunk_index: Mapped[int] = mapped_column(Integer)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="document_chunks_order"),
        CheckConstraint("chunk_index >= 0", name="document_chunks_index_valid"),
        CheckConstraint("page_number IS NULL OR page_number > 0", name="document_chunks_page_valid"),
    )


class IssueEvidence(Base):
    __tablename__ = "issue_evidence"
    issue_id: Mapped[UUID] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_type: Mapped[str] = mapped_column(String(40))
    __table_args__ = (
        Index("issue_evidence_chunk", "chunk_id"),
        CheckConstraint(
            "evidence_type IN ('possible_cause','diagnostic_procedure','resolution',"
            "'supporting_observation')",
            name="issue_evidence_type_valid",
        ),
    )
