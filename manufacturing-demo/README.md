# Manufacturing ML and MCP demo

A local synthetic manufacturing quality example. It trains a scikit-learn classifier from PostgreSQL records and exposes bounded REST endpoints and six MCP tools. It contains no generative model. `quality_label` is immutable ground truth; the 200-record stratified evaluation snapshot is frozen at seeding and excluded from training.

## Start

From this directory, ensure the repository root `.env` contains `MANUFACTURING_DB_PASSWORD` and `MANUFACTURING_API_KEY` (at least 16 characters each), then run:

```sh
docker compose --env-file ../.env up -d --build --wait
```

The API is at `http://localhost:8100`; MCP Streamable HTTP is at `http://localhost:8100/mcp`. Docker clients on the shared `meta-harness-mcp` network use `http://manufacturing-ml:8000/mcp`. The database is private to Compose. PostgreSQL and trained artifacts persist in named volumes. Root `.env` is not copied into the image.

To register it in Meta-Harness, open **MCP → Add MCP Server**, enter the URL above (use the Docker service URL when core is containerized), choose Bearer Token, and reference `MANUFACTURING_API_KEY`. Test, discover tools, save, select permitted tools, and enable the server for chat. Read-only tools run normally; training asks for confirmation.

For container-to-container access, create the shared `meta-harness-mcp` network once if needed, and start/recreate Meta-Harness core with the root `docker-compose.mcp.yml` overlay. Keep that overlay on subsequent core Compose commands. The root [operations guide](../docs/OPERATIONS.md) documents both stack commands and exact-origin configuration.

## Data, training and API

Startup idempotently seeds 1,000 deterministic synthetic rows. Positive label `1` means Good; `0` means Defective. The immutable held-out set is 200 rows; the remaining 800 seed rows are eligible for training. For example:

```sh
curl -H "Authorization: Bearer $MANUFACTURING_API_KEY" http://localhost:8100/ready
curl -H "Authorization: Bearer $MANUFACTURING_API_KEY" -H 'Content-Type: application/json' \
  -d '{"temperature":82.5,"pressure":5.8,"vibration":0.65,"production_speed":130,"humidity":48,"material_quality":0.74}' \
  http://localhost:8100/api/model/predict
curl -H "Authorization: Bearer $MANUFACTURING_API_KEY" http://localhost:8100/api/model/metrics
```

Training uses a background job and atomically replaces the model only after successful validation. The MCP `train_quality_model` starts a job; poll `get_training_status` and then retrieve `get_quality_model_metrics`. New explicitly approved labeled rows may be added by an operator directly to the database; API/MCP do not edit labels. Dataset queries are paginated and bounded; predictions never overwrite labels. Swagger is at `/docs` and requires bearer authentication.

REST routes: `GET /health`, `GET /ready`, `POST /api/model/train`, `GET /api/model/status`, `GET /api/model/metrics`, `POST /api/model/predict`, `POST /api/model/predict-batch`, `POST /api/model/evaluate`, `GET /api/dataset`, `GET /api/dataset/predictions`, and `GET /api/dataset/statistics`.

## Reset and tests

Reset is destructive to this demo's database and model volume. Stop the stack, remove only this Compose project's volumes with `docker compose --env-file ../.env down -v`, then start it again to reseed. Do not use this command against shared/production data.

The isolated database-backed test stack is defined in `docker-compose.test.yml`; run `docker compose -f docker-compose.test.yml up --build --abort-on-container-exit`, then `docker compose -f docker-compose.test.yml down -v`. It uses a separate disposable PostgreSQL database. Locked runtime and test dependencies are in `requirements*.lock`.

Module ownership: `db.py` schema/sessions; `seed.py` reproducible seed and frozen holdout; `dataset.py` bounded queries; `model.py` training, artifact lifecycle and inference; `api.py` REST/auth/logging; `mcp_server.py` MCP schemas and shared service calls; `cli.py` operational commands. Configuration is in `config.py` and `manufacturing-demo/.env.example`.

> **Superseded at runtime (2026-10-09):** Use [zsk-service](../zsk-service/README.md). The dedicated DB volume was reused and the old product/evaluation tables removed at the user’s request. Do not restart this historical service against that volume. Its code and old artifact volume are retained as historical implementation.
