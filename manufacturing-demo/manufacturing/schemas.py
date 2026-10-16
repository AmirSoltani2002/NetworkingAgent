from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

FEATURES = ["temperature", "pressure", "vibration", "production_speed", "humidity", "material_quality"]


class Features(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    temperature: float = Field(ge=-50, le=250)
    pressure: float = Field(ge=0, le=30)
    vibration: float = Field(ge=0, le=10)
    production_speed: float = Field(ge=0, le=1000)
    humidity: float = Field(ge=0, le=100)
    material_quality: float = Field(ge=0, le=1)


class Prediction(BaseModel):
    predicted_label: int
    classification: str
    probability_defective: float
    probability_good: float
    model_version: str


class BatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[Features] = Field(min_length=1, max_length=500)


class TrainingConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    regularization_c: float = Field(default=1.0, gt=0, le=100)
    max_iterations: int = Field(default=500, ge=100, le=2000)


class TrainInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    use_all_approved_training_data: bool = True
    configuration: TrainingConfiguration = Field(default_factory=TrainingConfiguration)

    @field_validator("use_all_approved_training_data")
    @classmethod
    def approved(cls, value):
        if not value:
            raise ValueError("Only the approved training partition is supported")
        return value


class DatasetFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=100000)
    machine_id: str | None = Field(default=None, max_length=20)
    quality_label: int | None = Field(default=None, ge=0, le=1)
    predicted_label: int | None = Field(default=None, ge=0, le=1)
    start_date: datetime | None = None
    end_date: datetime | None = None

    @field_validator("start_date", "end_date")
    @classmethod
    def utc(cls, value):
        return value.replace(tzinfo=timezone.utc) if value and not value.tzinfo else value

    @field_validator("end_date")
    @classmethod
    def dates(cls, value, info):
        start = info.data.get("start_date")
        if start and value and start > value:
            raise ValueError("end_date must be after start_date")
        return value
