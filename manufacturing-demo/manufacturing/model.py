import hashlib
import json
import logging
import math
import os
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select, text, update

from .db import EvaluationProduct, Product, TrainingJob
from .errors import ServiceError
from .schemas import FEATURES, TrainInput

logger = logging.getLogger("manufacturing")


def evaluation_metrics(model, records):
    frame = pd.DataFrame([row.features for row in records], columns=FEATURES)
    actual = [row.quality_label for row in records]
    predicted = model.predict(frame)
    return {"accuracy": float(accuracy_score(actual, predicted)),
            "precision": float(precision_score(actual, predicted, zero_division=0)),
            "recall": float(recall_score(actual, predicted, zero_division=0)),
            "f1_score": float(f1_score(actual, predicted, zero_division=0)),
            "confusion_matrix": confusion_matrix(actual, predicted, labels=[0, 1]).tolist(),
            "confusion_matrix_labels": ["Defective (0)", "Good (1)"], "positive_class": "Good (1)",
            "defective_precision": float(precision_score(actual, predicted, pos_label=0, zero_division=0)),
            "defective_recall": float(recall_score(actual, predicted, pos_label=0, zero_division=0)),
            "evaluation_sample_count": len(records),
            "majority_baseline_accuracy": float(max(np.mean(np.array(actual) == 0), np.mean(np.array(actual) == 1)))}


def test_fingerprint(records):
    values = [{"product_id": r.product_id, "features": r.features, "quality_label": r.quality_label} for r in records]
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


class ModelService:
    def __init__(self, engine, sessions, settings):
        self.engine, self.sessions, self.settings = engine, sessions, settings
        settings.artifact_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = settings.artifact_dir / "active.joblib"
        self._cache = None
        self._stamp = None
        self._mutex = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def bundle(self):
        if not self.path.exists():
            raise ServiceError("MODEL_NOT_TRAINED", "Train the model before requesting inference", 503)
        with self._mutex:
            stat = self.path.lstat()
            if self.path.is_symlink() or stat.st_uid != os.getuid():
                raise ServiceError("UNTRUSTED_ARTIFACT", "Model artifacts must be owned by the service user", 503)
            stamp = (stat.st_ino, stat.st_mtime_ns)
            if stamp != self._stamp:
                try:
                    value = joblib.load(self.path)
                    if value["features"] != FEATURES or value["sklearn_version"] != sklearn.__version__:
                        raise ValueError()
                    self._cache, self._stamp = value, stamp
                except Exception:
                    raise ServiceError("INVALID_ARTIFACT", "Model artifact is incompatible; retrain with this service version", 503) from None
            return self._cache

    def start(self):
        self._thread = threading.Thread(target=self._worker, name="model-training", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def submit(self, request: TrainInput):
        with self.sessions.begin() as session:
            session.execute(text("SELECT pg_advisory_xact_lock(19378143)"))
            existing = session.scalar(select(TrainingJob).where(TrainingJob.status.in_(["queued", "running"])))
            if existing:
                raise ServiceError("TRAINING_BUSY", f"Training job {existing.id} is already active", 409)
            job = TrainingJob(id=str(uuid4()), status="queued", configuration=request.configuration.model_dump())
            session.add(job)
        return {"job_id": job.id, "status": job.status}

    def job(self, identifier):
        with self.sessions() as session:
            job = session.get(TrainingJob, identifier)
            if not job:
                raise ServiceError("JOB_NOT_FOUND", "Training job not found", 404)
            return {"job_id": job.id, "status": job.status, "model_version": job.model_version,
                    "training_sample_count": job.training_sample_count, "metrics": job.metrics,
                    "created_at": job.created_at.isoformat(),
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None, "error": job.error}

    def status(self):
        with self.sessions() as session:
            latest = session.scalar(select(TrainingJob).order_by(TrainingJob.created_at.desc()).limit(1))
        try:
            bundle = self.bundle()
            deployed = {k: bundle[k] for k in ["model_version", "training_timestamp", "training_sample_count", "metrics", "test_fingerprint"]}
            status = "ready"
        except ServiceError as error:
            if error.code != "MODEL_NOT_TRAINED":
                raise
            deployed, status = None, "untrained"
        return {"status": status, "deployed_model": deployed, "latest_job": self.job(latest.id) if latest else None}

    def metrics(self):
        bundle = self.bundle()
        return {**bundle["metrics"], "model_version": bundle["model_version"],
                "training_timestamp": bundle["training_timestamp"], "training_sample_count": bundle["training_sample_count"],
                "test_fingerprint": bundle["test_fingerprint"], "dataset": "synthetic; fixed held-out evaluation"}

    def evaluate_model(self):
        bundle = self.bundle()
        with self.sessions() as session:
            records = session.scalars(select(EvaluationProduct).order_by(EvaluationProduct.product_id)).all()
        if test_fingerprint(records) != bundle["test_fingerprint"]:
            raise ServiceError("TEST_PARTITION_CHANGED", "Held-out snapshot differs from the deployed model", 409)
        return {**evaluation_metrics(bundle["pipeline"], records), "model_version": bundle["model_version"]}

    def predict(self, rows):
        bundle = self.bundle()
        probabilities = bundle["pipeline"].predict_proba(pd.DataFrame(rows, columns=FEATURES))
        classes = list(bundle["pipeline"].classes_)
        return [{"predicted_label": int(classes[int(np.argmax(p))]),
                 "classification": "Good" if classes[int(np.argmax(p))] == 1 else "Defective",
                 "probability_defective": float(p[classes.index(0)]), "probability_good": float(p[classes.index(1)]),
                 "model_version": bundle["model_version"]} for p in probabilities]

    def train_model(self, job_id):
        raise ServiceError("TRAINING_LABELS_REMOVED", "Ground-truth labels were removed from production records; retraining is unavailable")

    def _worker(self):
        # One application process/worker owns the queue. API inference uses independent connections and cache.
        with self.engine.connect() as lock:
            acquired = lock.scalar(text("SELECT pg_try_advisory_lock(19378144)"))
            lock.commit()
            if not acquired:
                logger.error(json.dumps({"event": "training_worker_already_active"}))
                return
            try:
                with self.sessions.begin() as session:
                    if self.path.exists():
                        bundle = self.bundle()
                        session.execute(update(TrainingJob).where(TrainingJob.id == bundle["job_id"]).values(status="ready",
                            model_version=bundle["model_version"], training_sample_count=bundle["training_sample_count"],
                            metrics=bundle["metrics"], completed_at=datetime.now(timezone.utc)))
                    session.execute(update(TrainingJob).where(TrainingJob.status == "running").values(status="failed",
                        error="Training interrupted by service restart; request a new job", completed_at=datetime.now(timezone.utc)))
                while not self._stop.is_set():
                    with self.sessions.begin() as session:
                        job = session.scalar(select(TrainingJob).where(TrainingJob.status == "queued").order_by(TrainingJob.created_at).limit(1))
                        identifier = job.id if job else None
                        if job:
                            job.status = "running"
                    if not identifier:
                        self._stop.wait(0.25)
                        continue
                    try:
                        self.train_model(identifier)
                    except Exception:
                        with self.sessions.begin() as session:
                            session.execute(update(TrainingJob).where(TrainingJob.id == identifier).values(status="failed",
                                error="Training failed; inspect approved data or artifact storage and retry", completed_at=datetime.now(timezone.utc)))
                        logger.error(json.dumps({"event": "training_failed", "job_id": identifier}))
            except Exception:
                logger.error(json.dumps({"event": "training_worker_failed"}))
            finally:
                lock.execute(text("SELECT pg_advisory_unlock(19378144)"))
                lock.commit()
