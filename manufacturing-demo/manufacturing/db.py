from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, Integer, String, create_engine, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "manufacturing_products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    production_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    machine_id: Mapped[str] = mapped_column(String(20), index=True)
    temperature: Mapped[float] = mapped_column(Float)
    pressure: Mapped[float] = mapped_column(Float)
    vibration: Mapped[float] = mapped_column(Float)
    production_speed: Mapped[float] = mapped_column(Float)
    humidity: Mapped[float] = mapped_column(Float)
    material_quality: Mapped[float] = mapped_column(Float)
    __table_args__ = (
        CheckConstraint("material_quality BETWEEN 0 AND 1 AND humidity BETWEEN 0 AND 100 AND pressure >= 0 AND vibration >= 0 AND production_speed >= 0", name="valid_measurements"),
    )


class EvaluationProduct(Base):
    """Frozen original measurements/labels. No FK: deleting production data cannot change evaluation."""
    __tablename__ = "evaluation_products"
    product_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB)
    quality_label: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint("quality_label IN (0,1)"),)


class TrainingJob(Base):
    __tablename__ = "training_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default="queued")
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    model_version: Mapped[str | None] = mapped_column(String(50))
    training_sample_count: Mapped[int | None] = mapped_column(Integer)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("status IN ('queued','running','ready','failed')"),)


def database(settings):
    engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=8, max_overflow=4,
                           connect_args={"connect_timeout": 5, "options": "-c statement_timeout=15000"})
    return engine, sessionmaker(engine, expire_on_commit=False)
