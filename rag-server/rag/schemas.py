import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20000)]
EvidenceType = Literal["possible_cause", "diagnostic_procedure", "resolution", "supporting_observation"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MetadataInput(Input):
    metadata: dict = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def safe_metadata(cls, value):
        if any(key.startswith("_") for key in value):
            raise ValueError("Metadata keys beginning with '_' are reserved")
        if len(json.dumps(value, allow_nan=False).encode()) > 16384:
            raise ValueError("Metadata may contain at most 16 KiB")
        return value


class DeviceInput(MetadataInput):
    name: Short
    model: Short
    manufacturer: Short
    description: Long = ""


class IssueInput(Input):
    device_id: UUID
    title: Title
    category: Label
    symptoms: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]
    possible_cause: Long = ""
    description: Long = ""


class DocumentUpdate(MetadataInput):
    title: Title | None = None
    document_type: Label | None = None
    version: Label | None = None
    device_ids: list[UUID] | None = Field(None, max_length=100)

    @field_validator("title", "document_type", "version", "device_ids", "metadata", mode="before")
    @classmethod
    def no_explicit_null(cls, value):
        if value is None:
            raise ValueError("Omit unchanged fields rather than sending null")
        return value


class DocumentUpload(MetadataInput):
    title: Title
    document_type: Label
    version: Label = "1"
    device_ids: list[UUID] = Field(default_factory=list, max_length=100)


class EvidenceInput(Input):
    chunk_id: UUID
    evidence_type: EvidenceType


class SearchInput(Input):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    device_id: UUID | None = None
    device_name: Short | None = None
    device_model: Short | None = None
    issue_category: Label | None = None
    document_type: Label | None = None
    document_ids: list[UUID] | None = Field(None, max_length=100)
    top_k: int | None = Field(None, ge=1, le=50)
