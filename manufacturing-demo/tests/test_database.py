import hashlib
import json

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from manufacturing.db import EvaluationProduct, Product
from manufacturing.schemas import FEATURES
from manufacturing.seed import initialize, synthetic_records


def test_seed_reproducible_and_feature_related():
    records = synthetic_records()
    assert records == synthetic_records()
    assert records != synthetic_records(seed=43)
    assert len(records) == 1000 and len({r["product_id"] for r in records}) == 1000
    assert {r["quality_label"] for r in records} == {0, 1}
    good = [r for r in records if r["quality_label"] == 1]
    bad = [r for r in records if r["quality_label"] == 0]
    assert min(len(good), len(bad)) > 200
    for field in ["temperature", "vibration"]:
        assert sum(r[field] for r in bad)/len(bad) > sum(r[field] for r in good)/len(good)
    assert sum(r["material_quality"] for r in good)/len(good) > sum(r["material_quality"] for r in bad)/len(bad)
    assert FEATURES == ["temperature", "pressure", "vibration", "production_speed", "humidity", "material_quality"]


def test_schema_idempotent_seed_and_binary_constraint(client, app):
    initialize(app.state.engine, app.state.sessions, app.state.test_settings)
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 1000
        assert session.scalar(select(func.count()).select_from(EvaluationProduct)) == 200
    with pytest.raises(IntegrityError):
        with app.state.engine.begin() as connection:
            connection.execute(text("UPDATE manufacturing_products SET quality_label=2 WHERE id=1"))
    assert client.get("/api/dataset/statistics").json()["total"] == 1000


def test_filters_pagination_and_ground_truth(client):
    response = client.get("/api/dataset?limit=7&offset=2&machine_id=M01&quality_label=0").json()
    assert len(response["items"]) == 7
    assert all(row["machine_id"] == "M01" and row["quality_label"] == 0 for row in response["items"])
    assert client.get("/api/dataset?limit=101").status_code == 422
    date = client.get("/api/dataset?start_date=2026-01-01T00:00:00Z&end_date=2026-01-01T01:00:00Z").json()
    assert date["total"] == 13
    assert client.get("/api/dataset?start_date=2026-01-02&end_date=2026-01-01").status_code == 422


def test_snapshot_is_immutable_on_reseed(client, app):
    with app.state.sessions() as session:
        rows = session.scalars(select(EvaluationProduct).order_by(EvaluationProduct.product_id)).all()
        before = [(r.product_id, r.features, r.quality_label) for r in rows]
    initialize(app.state.engine, app.state.sessions, app.state.test_settings)
    with app.state.sessions() as session:
        after = [(r.product_id, r.features, r.quality_label) for r in session.scalars(select(EvaluationProduct).order_by(EvaluationProduct.product_id))]
    assert before == after
