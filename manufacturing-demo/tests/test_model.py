import threading
from unittest.mock import patch

import pytest
from sqlalchemy import select, update

from manufacturing.db import EvaluationProduct, Product, TrainingJob
from manufacturing.errors import ServiceError
from manufacturing.model import ModelService
from manufacturing.schemas import FEATURES, TrainInput
from tests.conftest import wait_for_job

INPUT = {"temperature": 82.5, "pressure": 5.8, "vibration": 0.65,
         "production_speed": 130, "humidity": 48, "material_quality": 0.74}


def test_training_evaluation_no_leakage_and_persistence(trained, app):
    bundle = trained.bundle()
    with app.state.sessions() as session:
        test_ids = set(session.scalars(select(EvaluationProduct.product_id)))
    assert len(bundle["training_product_ids"]) == 800
    assert not test_ids.intersection(bundle["training_product_ids"])
    assert bundle["pipeline"].feature_names_in_.tolist() == FEATURES
    # Preprocessor sees only training data, not the held-out population.
    assert bundle["pipeline"]["scale"].n_samples_seen_ == 800
    metrics = trained.metrics()
    assert sum(map(sum, metrics["confusion_matrix"])) == 200
    assert metrics["accuracy"] > metrics["majority_baseline_accuracy"]
    assert trained.evaluate_model()["accuracy"] == metrics["accuracy"]
    reloaded = ModelService(app.state.engine, app.state.sessions, app.state.test_settings)
    assert reloaded.predict([INPUT]) == trained.predict([INPUT])


def test_actual_inference_and_batch(trained, client):
    output = client.post("/api/model/predict", json=INPUT).json()
    assert output["predicted_label"] in [0, 1]
    assert output["classification"] == ("Good" if output["predicted_label"] == 1 else "Defective")
    assert abs(output["probability_good"]+output["probability_defective"]-1) < 1e-10
    assert client.post("/api/model/predict-batch", json={"records": [INPUT, INPUT]}).json() == [output, output]
    assert client.post("/api/model/predict", json={**INPUT, "material_quality": 2}).status_code == 422
    assert client.post("/api/model/predict", json={**INPUT, "temperature": True}).status_code == 422
    assert client.post("/api/model/predict", json={"temperature": 80}).status_code == 422
    assert client.post("/api/model/predict-batch", json={"records": []}).status_code == 422


def test_retraining_stable_test_excludes_modified_test_products(trained, app):
    before = trained.bundle()
    with app.state.sessions.begin() as session:
        test = session.scalar(select(EvaluationProduct))
        session.execute(update(Product).where(Product.product_id == test.product_id).values(temperature=110, quality_label=1-test.quality_label))
        data = {"product_id": "NEW0001", "machine_id": "M01", "production_timestamp": session.scalar(select(Product.production_timestamp).limit(1)),
                **INPUT, "quality_label": 0}
        session.add(Product(**data))
    result = wait_for_job(trained, trained.submit(TrainInput())["job_id"])
    assert result["status"] == "ready"
    after = trained.bundle()
    assert after["model_version"] != before["model_version"]
    assert after["training_sample_count"] == 801
    assert after["test_fingerprint"] == before["test_fingerprint"]
    assert test.product_id not in after["training_product_ids"]


def test_failure_preserves_old_model_and_nonblocking_inference(trained, app):
    old = trained.bundle()["model_version"]
    entered, release = threading.Event(), threading.Event()
    original = trained.train_model
    def slow_fail(_identifier):
        entered.set()
        release.wait(5)
        raise ValueError("sensitive internal failure")
    with patch.object(trained, "train_model", slow_fail):
        job = trained.submit(TrainInput())
        assert entered.wait(5)
        assert trained.predict([INPUT])[0]["model_version"] == old
        with pytest.raises(ServiceError, match="already active"):
            trained.submit(TrainInput())
        release.set()
        failed = wait_for_job(trained, job["job_id"])
    assert failed["status"] == "failed" and "sensitive" not in failed["error"]
    assert trained.bundle()["model_version"] == old


def test_dataset_classification_no_ground_truth_changes(trained, client, app):
    with app.state.sessions() as session:
        before = session.execute(select(Product.id, Product.quality_label).order_by(Product.id)).all()
    response = client.get("/api/dataset/predictions?predicted_label=0&limit=11&offset=3").json()
    assert len(response["items"]) == 11 and response["statistics"]["population_count"] == 1000
    assert response["total"] == response["statistics"]["predicted_defective"]
    assert all(r["predicted_label"] == 0 and r["correct_prediction"] == (r["actual_label"] == 0) for r in response["items"])
    with app.state.sessions() as session:
        assert before == session.execute(select(Product.id, Product.quality_label).order_by(Product.id)).all()


def test_untrained_model_and_missing_job(client, app):
    assert client.post("/api/model/predict", json=INPUT).status_code == 503
    assert client.get("/api/model/status").json()["status"] == "untrained"
    assert client.get("/api/model/status?job_id=missing").status_code == 404
