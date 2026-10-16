import os
import secrets
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from manufacturing.api import create_app
from manufacturing.config import Settings


@pytest.fixture
def app(tmp_path):
    name = os.getenv("MANUFACTURING_DB_NAME", "manufacturing_test")
    assert name.endswith("_test"), "Refuse destructive tests against a non-test database"
    settings = Settings(db_name=name, artifact_dir=tmp_path, api_key=secrets.token_hex(24),
                        mcp_allowed_hosts="127.0.0.1:*,localhost:*,testserver")
    application = create_app(settings)
    from manufacturing.db import Base
    Base.metadata.create_all(application.state.engine)
    with application.state.engine.begin() as connection:
        connection.execute(text("TRUNCATE training_jobs, evaluation_products, manufacturing_products RESTART IDENTITY"))
    application.state.test_settings = settings
    return application


@pytest.fixture
def client(app):
    with TestClient(app, headers={"Authorization": f"Bearer {app.state.test_settings.api_key.get_secret_value()}"}) as client:
        yield client


def wait_for_job(model, identifier):
    deadline = time.monotonic()+15
    while time.monotonic()<deadline:
        result = model.job(identifier)
        if result["status"] in ["ready", "failed"]:
            return result
        time.sleep(0.03)
    raise AssertionError("Training did not complete")


@pytest.fixture
def trained(client, app):
    result = client.post("/api/model/train", json={}).json()
    assert wait_for_job(app.state.model, result["job_id"])["status"] == "ready"
    return app.state.model
