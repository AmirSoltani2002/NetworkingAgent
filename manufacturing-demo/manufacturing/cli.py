import argparse
import logging
from pydantic import ValidationError

import uvicorn
from sqlalchemy import text

from .api import create_app
from .config import Settings
from .db import database
from .seed import initialize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["api", "seed", "reset"], nargs="?", default="api")
    parser.add_argument("--confirm-reset", action="store_true")
    args = parser.parse_args()
    try:
        settings = Settings()
    except ValidationError:
        raise SystemExit("Invalid manufacturing environment configuration; check required secrets and settings") from None
    logging.basicConfig(level=settings.log_level, format="%(message)s")
    if args.command == "api":
        uvicorn.run(create_app(settings), host="0.0.0.0", port=settings.port, workers=1,
                    access_log=False, log_level=settings.log_level.lower(), timeout_graceful_shutdown=15)
        return
    engine, sessions = database(settings)
    if args.command == "reset":
        if not args.confirm_reset:
            parser.error("reset deletes demo records, jobs and models; pass --confirm-reset")
        with engine.begin() as connection:
            # Only the manufacturing demo schema; never accept arbitrary SQL from REST/MCP.
            connection.execute(text("TRUNCATE training_jobs, evaluation_products, manufacturing_products RESTART IDENTITY"))
        for path in settings.artifact_dir.glob("*"):
            if path.is_file() and not path.is_symlink():
                path.unlink()
    initialize(engine, sessions, settings)
    engine.dispose()
    print("Synthetic manufacturing dataset initialized (idempotent).")


if __name__ == "__main__":
    main()
