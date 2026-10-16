-- Independent synthetic future-onset model. Does not restore historical labels.
CREATE TABLE zsk_forecast_models (
 version UUID PRIMARY KEY, horizon_minutes INTEGER NOT NULL CHECK(horizon_minutes BETWEEN 5 AND 120),
 artifact_sha256 TEXT NOT NULL, metrics JSONB NOT NULL, active BOOLEAN NOT NULL DEFAULT false,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX zsk_one_active_forecast ON zsk_forecast_models(active) WHERE active;
