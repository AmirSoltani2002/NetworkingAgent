import os

import pytest

# Credentials come from the test runner/environment, never usable committed defaults.
os.environ.setdefault("RAG_AUTH_REQUIRED", "false")


@pytest.fixture(scope="session")
def database():
    from alembic import command
    from alembic.config import Config

    from rag.config import Settings
    from rag.db import Database

    settings = Settings()
    if not settings.db_name.endswith(("_test", "_tests")):
        raise RuntimeError("Tests require an isolated database name ending in _test or _tests")
    command.upgrade(Config("alembic.ini"), "head")
    db = Database(settings)
    db.check_contract()
    yield db
    db.engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(database):
    from sqlalchemy import text

    with database.engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE devices, issues, documents, device_documents, document_chunks, issue_evidence CASCADE"
            )
        )
    yield


@pytest.fixture
def embeddings():
    from tests.fakes import FakeEmbeddings

    return FakeEmbeddings()


@pytest.fixture
def client(database, embeddings, tmp_path):
    from fastapi.testclient import TestClient

    from rag.api import create_app
    from rag.config import Settings

    settings = Settings(storage_dir=tmp_path, auth_required=False)
    with TestClient(create_app(settings, embeddings, database)) as client:
        yield client
