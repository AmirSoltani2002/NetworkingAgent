from alembic import context
from sqlalchemy import create_engine
from rag.config import Settings
from rag.models import Base

settings = Settings()
if context.is_offline_mode():
    context.configure(
        url=settings.database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(settings.database_url, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            # Concurrent API/worker startup cannot race migrations.
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(7740827)")
            context.run_migrations()
    engine.dispose()
