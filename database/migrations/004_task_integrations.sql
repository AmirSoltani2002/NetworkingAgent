-- Authenticated, template-bound external events, separate from removed trigger UI.
CREATE TABLE IF NOT EXISTS task_integration_receipts (
 source TEXT NOT NULL,event_id UUID NOT NULL,fingerprint TEXT NOT NULL,
 task_id UUID NOT NULL REFERENCES agent_tasks(id),created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(source,event_id)
);
