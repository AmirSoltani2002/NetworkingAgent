import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

from .config import Settings
from .observability import configure_logging


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["api", "worker", "worker-health", "migrate", "download-models"])
    args = parser.parse_args()
    try:
        settings = Settings()
    except Exception:
        print(
            "Invalid RAG configuration: check required secrets, authentication, dimensions and documented limits",
            file=sys.stderr,
        )
        return 1
    configure_logging(settings.logging_level)
    if args.command == "worker-health":
        heartbeat = Path("/tmp/rag-worker-heartbeat")
        try:
            from sqlalchemy import text

            from .db import Database

            if time.time() - heartbeat.stat().st_mtime > 60:
                return 1
            db = Database(settings)
            with db.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            db.engine.dispose()
            return 0
        except Exception:
            return 1
    if args.command in {"api", "worker", "migrate"}:
        from alembic import command
        from alembic.config import Config

        try:
            command.upgrade(Config("alembic.ini"), "head")
            from .db import Database

            db = Database(settings)
            db.check_contract()
        except Exception:
            logging.getLogger("rag").error(
                "startup_database_failed", extra={"event": "startup_database_failed"}
            )
            print(
                "Database/migration/embedding contract check failed; verify connection and model configuration",
                file=sys.stderr,
            )
            return 1
        if args.command == "migrate":
            db.engine.dispose()
            return 0
    try:
        if args.command == "api":
            import uvicorn

            from .api import create_app

            uvicorn.run(
                create_app(settings, database=db),
                host="0.0.0.0",
                port=settings.port,
                access_log=False,
                log_config=None,
                timeout_graceful_shutdown=30,
            )
            db.engine.dispose()
            return 0
        from .embeddings import LocalEmbeddings, LocalReranker

        embeddings = LocalEmbeddings(settings)
        if args.command == "download-models":
            if settings.reranker_enabled:
                LocalReranker(settings)
            return 0
        from .worker import IngestionWorker

        worker = IngestionWorker(db, settings, embeddings)
        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        heartbeat = Path("/tmp/rag-worker-heartbeat")

        def beat():
            while not stop.is_set():
                heartbeat.touch(mode=0o600)
                stop.wait(5)

        thread = threading.Thread(target=beat, daemon=True)
        thread.start()
        worker.documents.sweep_orphans()
        last_sweep = time.monotonic()
        while not stop.is_set():
            try:
                handled = worker.run_once()
                if time.monotonic() - last_sweep > 3600:
                    worker.documents.sweep_orphans()
                    last_sweep = time.monotonic()
                if not handled:
                    stop.wait(settings.worker_poll_seconds)
            except Exception as error:
                logging.getLogger("rag").error(
                    "worker_cycle_failed",
                    extra={"event": "worker_cycle_failed", "error_type": type(error).__name__},
                )
                stop.wait(settings.worker_poll_seconds)
        thread.join(timeout=6)
        db.engine.dispose()
        return 0
    except Exception as error:
        logging.getLogger("rag").error(
            "startup_failed", extra={"event": "startup_failed", "error_type": type(error).__name__}
        )
        print(
            "Local model/service startup failed; check the model cache, pinned revision and device configuration",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
