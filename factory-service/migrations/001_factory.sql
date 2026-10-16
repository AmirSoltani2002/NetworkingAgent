-- Additive manufacturing-only schema; existing ZSK rows/models remain untouched.
CREATE TABLE factory_state (
 id INTEGER PRIMARY KEY CHECK(id=1), version BIGINT NOT NULL DEFAULT 1,
 state JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE factory_measurements (
 id BIGINT PRIMARY KEY REFERENCES zsk_unlabeled_measurements(id), epoch UUID NOT NULL,
 simulation_timestamp TIMESTAMPTZ NOT NULL, ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 machine_state TEXT NOT NULL, simulation_minute DOUBLE PRECISION NOT NULL
);
CREATE INDEX factory_measurements_epoch_time ON factory_measurements(epoch,simulation_timestamp);
-- Truth is confined to this table; it is never selected by inference/input tools.
CREATE TABLE factory_ground_truth (
 measurement_id BIGINT PRIMARY KEY REFERENCES factory_measurements(id), health_label INTEGER NOT NULL CHECK(health_label IN(0,1)),
 scenarios JSONB NOT NULL, synthetic_only BOOLEAN NOT NULL DEFAULT true
);
CREATE TABLE simulation_events (
 sequence BIGSERIAL PRIMARY KEY, event_id UUID NOT NULL UNIQUE, type TEXT NOT NULL,
 epoch UUID NOT NULL, simulation_timestamp TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE factory_actions (
 id UUID PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL,
 kind TEXT NOT NULL, arguments JSONB NOT NULL, status TEXT NOT NULL,
 previous_state JSONB NOT NULL, new_state JSONB NOT NULL, result JSONB NOT NULL,
 simulation_timestamp TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), completed_at TIMESTAMPTZ
);
CREATE TABLE machine_alarms (
 id UUID PRIMARY KEY, epoch UUID NOT NULL, machine_id TEXT NOT NULL, alarm_type TEXT NOT NULL,
 component TEXT NOT NULL, severity TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new',
 details JSONB NOT NULL, agent_task_id UUID, agent_status TEXT, agent_activity JSONB,
 simulation_timestamp TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX factory_alarm_active ON machine_alarms(epoch,alarm_type,component,status);
CREATE TABLE monitoring_checkpoints (
 epoch UUID PRIMARY KEY, last_measurement_id BIGINT NOT NULL DEFAULT 0,
 next_due_minute DOUBLE PRECISION NOT NULL, status TEXT NOT NULL DEFAULT 'ready',
 last_error TEXT, attempts INTEGER NOT NULL DEFAULT 0, retry_at TIMESTAMPTZ, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE factory_predictions (
 measurement_id BIGINT PRIMARY KEY REFERENCES factory_measurements(id),
 current_condition JSONB NOT NULL, forecast JSONB, processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE factory_outbox (
 event_id UUID PRIMARY KEY REFERENCES machine_alarms(id), payload JSONB NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(), last_error TEXT, task_id UUID,
 delivered_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS factory_migrations (name TEXT PRIMARY KEY, checksum TEXT NOT NULL);
