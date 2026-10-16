import json
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .errors import ServiceError


class Database:
    def __init__(self, settings):
        self.settings = settings
        self.engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            connect_args={"connect_timeout": 5},
            hide_parameters=True,
        )
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self):
        with self.sessions.begin() as session:
            yield session

    def check_contract(self):
        with self.engine.connect() as connection:
            for table in ("issues", "document_chunks"):
                comment = connection.scalar(
                    text("SELECT obj_description(to_regclass(:table), 'pg_class')"), {"table": table}
                )
                dimension = connection.scalar(
                    text(
                        "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                        "WHERE attrelid=to_regclass(:table) AND attname='embedding'"
                    ),
                    {"table": table},
                )
                try:
                    contract = json.loads(comment or "{}")["embedding_contract"]
                except (ValueError, KeyError):
                    raise RuntimeError("Run Alembic migrations before starting the service") from None
                if (
                    contract != self.settings.embedding_contract
                    or dimension != f"vector({self.settings.embedding_dimension})"
                ):
                    raise RuntimeError(
                        "Embedding model/revision/dimension differs from the database contract; "
                        "use the original configuration or migrate and re-embed explicitly"
                    )

    @contextmanager
    def document_lock(self, document_id):
        # Keep the session lock connection alive across processing, never a transaction.
        with self.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:id, 7))"), {"id": str(document_id)}
            )
            if not acquired:
                raise ServiceError(409, "DOCUMENT_BUSY", "Document processing is in progress; retry later")
            try:
                yield
            finally:
                try:
                    connection.execute(
                        text("SELECT pg_advisory_unlock(hashtextextended(:id, 7))"), {"id": str(document_id)}
                    )
                except Exception:
                    connection.invalidate()
