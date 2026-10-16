# ZSK replacement verification — 2026-10-09

## Executed

- Built and deployed non-root `zsk-ml:local`; `zsk-db` reuses the existing dedicated manufacturing PostgreSQL volume. Chat/core/UI/RAG were not rebuilt or modified.
- Supplied baseline schema plus migrations 002/003 applied with checksums. Initial model trained from exactly 1,000 labeled rows using supplied RandomForest logic and unchanged 20-feature definition.
- Final database: **0 labeled training rows, 1,000 unlabeled rows, 1,000 separate predictions**. Original `manufacturing_products` and `evaluation_products` tables removed. Restart/recreation did not reimport labels or retrain the model.
- Actual evaluation candidate: 780 earlier-period training rows, 20-row embargo, 200 chronological holdout rows; accuracy **0.97**, balanced accuracy **0.9652738566**, macro precision **0.9517543860**, macro recall **0.9652738566**, macro F1 **0.9582811848**, confusion matrix label order [0,1]: **[[44,2],[4,150]]**. Final artifact fits all 1,000 labeled rows. Metrics describe the evaluation candidate, not an independent test of that final fit.
- Isolated `zsk_tests` regression script passed on the final migration set: actual training, lifecycle/seed idempotency, labels removed, 1,000 actual stored predictions, **all 1,000 probabilities equal full-history inference**, single most-recent reading parity, append validation/idempotency/duplicates, no-label training refusal, key conflict, missing history and temporal-order rejection. Output: [zsk-tests.log](zsk-tests.log).
- Live FastAPI/official Python MCP SDK checks passed: read/admin authentication, unauthorized training, required fields/bounded pagination, eight discovered tools, stored measurement prediction, asynchronous batch status, 1,000 stored outputs and stable-key duplicate detection: [zsk-mcp.json](zsk-mcp.json).
- Existing generic registry profile updated in place, preserving its ID/URL alias. Eight tools discovered; five read-only tools explicitly enabled using ZSK_API_KEY. Admin write tools remain unapproved. Source remains generic.
- Actual saved gpt-6-luna/Instant agent called `predict_zsk_health` and `get_zsk_model_metrics` successfully. Measurement 1000: Healthy / label 1, fault probability 0.0, history_count 2, same active model version. Saved trace: [zsk-agent.json](zsk-agent.json).
- Initial agent check exposed a schema compatibility issue: core intentionally rejects regex schema constraints. Fixed external machine-ID validation to bounded character validation without publishing regex. Initial failure remains truthfully in the review conversation; subsequent two calls succeeded. UUID/date MCP JSON serialization also fixed before final checks. No core security rule was relaxed.
- Existing core health, task listing and both RAG/ZSK MCP registrations returned 200/connected. Existing MCP screen captured and inspected: [ui-zsk-mcp.png](../screenshots/ui-zsk-mcp.png); credential display hidden for publication. No UI styling changes.
- Python compilation and repository whitespace checks passed. Final deployed state: [zsk-final-state.json](zsk-final-state.json).

- Actual isolated container SIGKILL during running batch succeeded: resumed from checkpoint, attempts=2, 1,000 predictions, 0 labels, 1 model version. [Restart log](zsk-restart.log). The initial test used one-row batches and timed out while correctly resumed; rerun used ten-row batches and sufficient wait, then passed. Both isolated stacks were removed.

## Scope / limitations

These are synthetic measurements, not actual Coperion telemetry or validated diagnosis. No equipment controls exist. Old code/artifact volume remains historical; do not restart its service against the replaced DB. Future retraining needs new explicit verified labels (initial labels were intentionally purged). No prediction becomes ground truth.

The complete historical core/UI/RAG test suites were not rerun. The deployed agent demonstration covered read-only prediction/metrics; authorized retraining/additional-label agent flow and write-approval UI were not exercised against live data. CSV imports use supplied startup assets and validated JSON append; no arbitrary file/model/SQL upload API is provided. Distributed DB partition fencing and adversarial load tests are not claimed.
