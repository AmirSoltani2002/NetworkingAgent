ALTER TABLE zsk_labeled_measurements ADD COLUMN provenance TEXT NOT NULL DEFAULT 'synthetic' CHECK (provenance IN ('synthetic','verified_operator_label'));
ALTER TABLE zsk_unlabeled_measurements ADD COLUMN provenance TEXT NOT NULL DEFAULT 'synthetic' CHECK (provenance IN ('synthetic','unknown'));
CREATE TABLE zsk_jobs (
 id UUID PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('train','batch')), status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed')),
 request JSONB NOT NULL, progress INTEGER NOT NULL DEFAULT 0, result JSONB, error TEXT, attempts INTEGER NOT NULL DEFAULT 0,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX zsk_one_training ON zsk_jobs(kind) WHERE kind='train' AND status IN ('queued','running');
CREATE INDEX zsk_jobs_due ON zsk_jobs(status,created_at);
CREATE TABLE zsk_models (
 version UUID PRIMARY KEY, artifact_sha256 TEXT NOT NULL, metrics JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE zsk_state (id INTEGER PRIMARY KEY CHECK(id=1), phase TEXT NOT NULL CHECK(phase IN ('training','inference')), active_version UUID REFERENCES zsk_models(version));
CREATE TABLE zsk_requests (key TEXT PRIMARY KEY, kind TEXT NOT NULL, fingerprint TEXT NOT NULL, response JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE zsk_audit (id BIGSERIAL PRIMARY KEY, action TEXT NOT NULL, details JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
ALTER TABLE zsk_predictions ADD COLUMN job_id UUID REFERENCES zsk_jobs(id);
ALTER TABLE zsk_predictions ALTER COLUMN model_version TYPE UUID USING model_version::uuid;
ALTER TABLE zsk_predictions ADD CONSTRAINT zsk_predictions_model_fk FOREIGN KEY(model_version) REFERENCES zsk_models(version);
