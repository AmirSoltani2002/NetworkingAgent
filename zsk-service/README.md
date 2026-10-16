# ZSK synthetic condition-monitoring service

Replacement for the previous manufacturing demonstration; Meta-Harness chat, RAG and task databases are unchanged. This is a synthetic RandomForest demonstration, not Coperion telemetry, a validated fault-risk estimate or equipment control.

## Current lifecycle (latest user instruction)

1. Reuse the dedicated manufacturing PostgreSQL volume, not the chat database.
2. Apply the supplied `postgres_schema.sql` as migration 001, then versioned runtime upgrades.
3. Import exactly 1,000 supplied labeled readings, idempotently.
4. Background job calls the supplied `train()` implementation (safely extended to sort timestamps and embargo each machine). Features remain exactly ten signals, two recipe indicators and eight causal rolling statistics. Alarm, simulated fault, row ID, timestamp and labels are not features.
5. Validate the artifact, save an immutable version/checksum, atomically activate its database pointer.
6. In the same database transaction, remove trained labeled rows, remove the old `manufacturing_products` and `evaluation_products` tables, and import the 1,000 supplied unlabeled readings. Startup never restores deleted training labels.

This deliberately overrides the older extended prompt's instruction to keep both seed datasets permanently. Labeled table schema remains for future explicitly verified operator labels, but the initial training rows are gone. Retraining with no labels returns `NO_TRAINING_LABELS`; predictions are never used as targets. Successful later retraining also purges only its snapshot's training rows, preserving additions made while it ran. Supplied source CSV files remain in this checkout/image; removal applies to database rows and temporary training snapshots.

The initial `.joblib` referenced in the extended prompt was not provided. Initial training therefore builds it from the exact supplied code/CSV. `example_predictions.csv` is a reference format, never substituted for actual inference.

## Start / connection

Secrets: ignored root `.env` contains existing `MANUFACTURING_DB_PASSWORD`, new read-only `ZSK_API_KEY`, and write/admin `ZSK_ADMIN_API_KEY`. No fallback credentials. Stop the old manufacturing stack first, **without deleting volumes**:

```sh
cd manufacturing-demo
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.meta-harness.yml down
cd ../zsk-service
docker build -t zsk-ml:local .
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.meta-harness.yml up -d --build --wait
```

Compose uses external volume `manufacturing-demo_manufacturing-data`; override nonsecret `ZSK_DATABASE_VOLUME` if your existing dedicated volume differs. Never mount one PostgreSQL volume into two running database containers. Model artifacts use `zsk-demo_zsk-models`. New installations create the database volume first with `docker volume create manufacturing-demo_manufacturing-data`.

REST/MCP host: `http://127.0.0.1:8100`, MCP `/mcp`. Containerized core on `meta-harness-mcp`: `http://manufacturing-ml:8000/mcp` (retained compatibility alias), or `http://zsk-ml:8000/mcp` after approving that exact origin in root `MCP_ALLOWED_ORIGINS`. Core must use its existing MCP Compose overlay. No database port is published; no secrets enter browser assets.

In existing **MCP → Connections**, edit the old manufacturing profile; use the compatibility URL and env reference `ZSK_API_KEY`, test/discover, then select the five read-only tools and enable. Existing tool permissions reset because tool names changed. For append/training/batch writes, use a separately configured admin credential reference, explicitly allow those exact tools, and confirm calls through existing chat/task policies. A user prompt alone is not a broad write grant. No frontend changes are needed.

## Eight discoverable tools

- `get_zsk_measurements`: machine/time/source filters, page≥1, page_size 1–100, signals/provenance/units.
- `add_zsk_measurements`: 1–100 readings, exact units, stable idempotency key; admin only. Append timestamps after the last machine/source reading. Per-row duplicate/out-of-order rejection; accepted/rejected counts. Labels must have `verified_operator_label` provenance. No simulated-fault label input.
- `train_zsk_health_model`: admin, stable key, optional `{test_fraction:0.2,gap:20}`; asynchronous full retraining. At least 100 genuine labeled rows, both classes in chronological partitions. Never trains unlabeled rows.
- `get_zsk_training_status`: durable job ID; queued/running/completed/failed, actual row progress for batch jobs, result/errors/attempts.
- `get_zsk_model_metrics`: optional version; measured evaluation-candidate holdout metrics and label counts.
- `predict_zsk_health`: exactly one supplied measurement or stored measurement ID; preceding two same-machine readings fetched automatically, or validated explicit recent_history. New readings require two prior readings. Early stored rows explicitly report warmup windows.
- `batch_predict_zsk_health`: admin, stable key, bounded page_size, machine/time/source filters; returns job ID immediately. Snapshot freezes membership/version. Includes preceding two readings outside each page/date boundary. job_id inspects status.
- `get_zsk_predictions`: bounded pagination, job/version/machine filters, separate saved outputs; 0=Faulty, 1=Healthy.

Units are `rpm`, `%`, `A`, `kW`, `mm/s`, `degC` (three temperatures), `bar`, `kg/h`, matching names in `zsk/schemas.py`. Supplied naive timestamps are explicitly interpreted as UTC. New values must be finite and satisfy documented schema bounds. Both labeled and unlabeled source identities remain distinct.

REST `/health`, `/ready` are public dependency checks; all other routes require bearer authentication. `/docs` and `/openapi.json` are protected. Management: `GET/POST /api/measurements`, `GET /api/model/status`, `GET /api/model/metrics`, `POST /api/model/train`, `POST /api/model/predict`, `POST /api/model/rollback`, `POST /api/batch-predictions`, `GET /api/jobs/{id}`, `GET /api/predictions`. No arbitrary SQL/path/code or model-upload endpoint. Measurements are append-only through the API; generic destructive CRUD is deliberately absent.

Rollback takes `{model_version,idempotency_key}` with admin authentication, validates registered service-owned artifact/hash/schema before atomically changing active pointer. Filesystem artifacts may outlive a failed transaction; only registered versions can load. No uploaded/untrusted joblib is accepted.

## Reliability and evaluation

Stable-key request ledger commits writes/responses together, rejects key reuse with different inputs. Single background worker is protected by a PostgreSQL session advisory lock across instances; interrupted running jobs are requeued when a worker obtains that lock. Batch checkpoints and prediction rows commit together; unique source/measurement/model constraints prevent duplicate predictions. Model version equals durable training job ID, allowing training activation recovery without an additional version. Temporary database failures retry with bounded attempts/backoff; permanent errors are reported. The existing harness remains conservative about unknown external write outcomes: inspect this service's persisted jobs and use the original key, never blindly issue a new key.

Evaluation uses earlier labeled data with a 20-reading per-machine gap and a chronological 20% holdout. The evaluation candidate uses 780 training/200 test rows for the supplied single-machine dataset; the final deployed model then fits all 1,000 labeled rows, matching the supplied code. Metrics describe the earlier-period evaluation candidate, **not an independent test of the final all-labeled artifact**. Do not call retraining incremental fine-tuning. Synthetic fault separability can produce optimistic results; no industrial accuracy claim.

## Verification

```sh
docker compose --env-file ../.env -f docker-compose.test.yml up --abort-on-container-exit --exit-code-from tests
# Only remove this isolated test stack's data:
docker compose --env-file ../.env -f docker-compose.test.yml down -v
```

Tests use `zsk_tests` and refuse non-test DB names. `tests/check.py` executes actual PostgreSQL, actual RandomForest training, full 1,000-row inference, all-batch/single/boundary parity, label purge/restart-safe seeding, key conflicts, invalid order/history and append checks. `tests/http_check.py` tests real deployed REST and official MCP discovery/calls/auth/idempotency. For an actual isolated container SIGKILL/restart check run `python3 tests/restart_check.py` from this directory (requires Docker; uses only zsk_restart_tests). The optional test Docker target supports `pytest -q tests`. Current results and limitations are in `../docs/verification/zsk-results.md`.

Module map: `zsk_model.py` supplied feature/model logic; `schemas.py` validation/units; `db.py` migrations/idempotent seed; `service.py` ledger, causal history, jobs/artifact lifecycle; `auth.py` scopes; `mcp_server.py` SDK wrappers; `api.py` REST/lifespan/auth/timeouts; `config.py` env configuration; `cli.py` non-root server entrypoint. Old manufacturing source/artifact volume is retained as historical code; do not restart it against the replaced dataset.

## Separate simulator future-onset baseline

The user-authorized factory extension adds `zsk/synthetic.py`, `zsk/forecast.py` and additive migration `004_forecast.sql`. Existing current-health classifier, historical-label purge and read/admin boundaries remain unchanged. Read-authenticated `GET /api/forecast/metrics`, `POST /api/forecast/predict` and MCP `get_zsk_forecast_metrics` / `predict_zsk_future_failure` expose the separate versioned synthetic onset model. Inference needs the target and two preceding five-minute measurements; no ground-truth/future features. Registered horizon is configurable through root `ZSK_FORECAST_HORIZON_MINUTES` (default 30; 5–120 in five-minute increments). Bootstrap trains/chronologically evaluates independent generated episodes and atomically activates the evaluated candidate without refitting holdout; changing horizon creates a new candidate. `ZSK_FORECAST_BOOTSTRAP=false` retains the active model. See [factory README](../factory-service/README.md) for measured metrics, assumptions and limitations. This does not turn current classification into industrial prognosis.
