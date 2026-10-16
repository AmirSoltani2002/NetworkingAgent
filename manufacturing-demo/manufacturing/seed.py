"""Deterministic synthetic measurements, not real manufacturing observations."""
from datetime import datetime, timedelta, timezone

import numpy as np
from sklearn.model_selection import train_test_split
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from .db import Base, EvaluationProduct, Product
from .schemas import FEATURES


def synthetic_records(count=1000, seed=42):
    rng = np.random.default_rng(seed)
    temperature = np.clip(rng.normal(78, 10, count), 45, 120)
    pressure = np.clip(rng.normal(5.4, 0.8, count), 2, 9)
    vibration = rng.beta(2, 5, count) * 1.5
    speed = np.clip(rng.normal(120, 20, count), 60, 190)
    humidity = np.clip(rng.normal(48, 12, count), 10, 90)
    material = 0.45 + 0.55 * rng.beta(8, 2, count)
    # Physical risk relationships, with stochastic outcomes and residual measurement noise.
    risk = (-1.1 + 0.16 * (temperature - 78) + 5.0 * (vibration - 0.35)
            + 9.0 * (0.85 - material) + 1.5 * abs(pressure - 5.4)
            + 0.018 * (speed - 120) + 0.018 * (humidity - 48))
    defective_probability = 0.04 + 0.92 / (1 + np.exp(-risk))
    labels = (rng.random(count) >= defective_probability).astype(int)
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [{"product_id": f"P{i+1:04d}", "production_timestamp": origin + timedelta(minutes=i*5),
             "machine_id": f"M{i%5+1:02d}", "temperature": round(float(temperature[i]), 3),
             "pressure": round(float(pressure[i]), 3), "vibration": round(float(vibration[i]), 4),
             "production_speed": round(float(speed[i]), 3), "humidity": round(float(humidity[i]), 3),
             "material_quality": round(float(material[i]), 4), "quality_label": int(labels[i])}
            for i in range(count)]


def initialize(engine, sessions, settings):
    Base.metadata.create_all(engine)
    # Remove the training target from persisted production records; evaluation labels
    # remain isolated in the frozen holdout table.
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE manufacturing_products DROP COLUMN IF EXISTS quality_label"))
    with sessions.begin() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(19378142)"))
        records = synthetic_records(settings.sample_count, settings.seed)
        # Preserve existing measurements and prevent startup duplication.
        for offset in range(0, len(records), 1000):
            batch = [{key: value for key, value in row.items() if key != "quality_label"} for row in records[offset:offset+1000]]
            session.execute(insert(Product).values(batch).on_conflict_do_nothing(index_elements=["product_id"]))
        if session.scalar(select(func.count()).select_from(EvaluationProduct)) == 0:
            # Keep target labels only in the separate frozen evaluation snapshot.
            _, test = train_test_split(records, test_size=0.2, random_state=settings.seed,
                                       stratify=[r["quality_label"] for r in records])
            session.add_all([EvaluationProduct(product_id=r["product_id"], quality_label=r["quality_label"],
                                               features={k: r[k] for k in FEATURES}) for r in test])
