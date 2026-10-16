import json

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from rag.config import Settings
from rag.db import Database


def test_six_domain_tables_and_contract(database):
    tables = set(inspect(database.engine).get_table_names())
    assert tables == {
        "devices",
        "issues",
        "documents",
        "device_documents",
        "document_chunks",
        "issue_evidence",
        "alembic_version",
    }
    with database.engine.connect() as connection:
        comment = connection.scalar(text("SELECT obj_description('issues'::regclass, 'pg_class')"))
        assert json.loads(comment)["embedding_contract"] == database.settings.embedding_contract
        assert connection.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
        assert (
            connection.scalar(
                text(
                    "SELECT format_type(atttypid,atttypmod) FROM pg_attribute "
                    "WHERE attrelid='issues'::regclass AND attname='embedding'"
                )
            )
            == "vector(384)"
        )


def test_migration_repeat_and_downgrade(database):
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    assert set(inspect(database.engine).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    database.check_contract()


def test_incompatible_model_fails(database):
    incompatible = Settings(embedding_model="different-local-model")
    db = Database(incompatible)
    try:
        with pytest.raises(RuntimeError, match="differs"):
            db.check_contract()
    finally:
        db.engine.dispose()
