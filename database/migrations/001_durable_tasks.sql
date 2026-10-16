-- Durable task execution; same PostgreSQL database as conversations.
CREATE TABLE IF NOT EXISTS agent_tasks (
 id uuid PRIMARY KEY, conversation_id uuid NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
 message_id uuid REFERENCES messages(id) ON DELETE SET NULL, user_request text NOT NULL,
 goal text NOT NULL, plan jsonb NOT NULL DEFAULT '[]', criteria jsonb NOT NULL DEFAULT '[]',
 status varchar(24) NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','RUNNING','WAITING_APPROVAL','RETRYING','PAUSED','COMPLETED','FAILED','CANCELLED')),
 current_step integer NOT NULL DEFAULT 0, completed_steps jsonb NOT NULL DEFAULT '[]', progress integer NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
 next_action jsonb, result text, last_error text, retry_count integer NOT NULL DEFAULT 0,
 grants jsonb NOT NULL DEFAULT '[]', context_window jsonb, tokens_used bigint NOT NULL DEFAULT 0,
 active_ms bigint NOT NULL DEFAULT 0, turn_count integer NOT NULL DEFAULT 0,
 next_run_at timestamptz NOT NULL DEFAULT now(), lease_owner uuid, lease_until timestamptz,
 dedupe_key text UNIQUE, source jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS agent_task_message ON agent_tasks(message_id) WHERE message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS agent_tasks_claim ON agent_tasks(status,next_run_at,lease_until);
CREATE INDEX IF NOT EXISTS agent_tasks_conversation ON agent_tasks(conversation_id,created_at);
CREATE TABLE IF NOT EXISTS task_steps (
 id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
 step_index integer NOT NULL, kind text NOT NULL, status text NOT NULL,
 decision jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(task_id,step_index)
);
CREATE TABLE IF NOT EXISTS task_operations (
 id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
 step_id uuid NOT NULL REFERENCES task_steps(id) ON DELETE CASCADE, operation_key text NOT NULL,
 kind text NOT NULL, action jsonb NOT NULL, read_only boolean NOT NULL,
 policy_digest text NOT NULL, status text NOT NULL CHECK(status IN ('PREPARED','DISPATCHING','SUCCEEDED','FAILED','UNKNOWN','REJECTED')),
 result jsonb, attempts integer NOT NULL DEFAULT 0, last_error text, duration_ms bigint,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(task_id,operation_key)
);
CREATE INDEX IF NOT EXISTS task_operations_task ON task_operations(task_id,created_at);
CREATE TABLE IF NOT EXISTS task_approvals (
 id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
 operation_id uuid NOT NULL UNIQUE REFERENCES task_operations(id) ON DELETE CASCADE,
 action jsonb NOT NULL, policy_digest text NOT NULL, decision boolean,
 created_at timestamptz NOT NULL DEFAULT now(), decided_at timestamptz
);
CREATE TABLE IF NOT EXISTS task_verifications (
 id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
 criterion_id text NOT NULL, passed boolean NOT NULL, evidence jsonb NOT NULL, checked_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS task_verifications_task ON task_verifications(task_id,checked_at);
CREATE TABLE IF NOT EXISTS task_events (
 sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 task_id uuid NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE, type text NOT NULL, data jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS task_events_task ON task_events(task_id,sequence);
CREATE TABLE IF NOT EXISTS task_schedules (
 id uuid PRIMARY KEY, name text NOT NULL, kind text NOT NULL CHECK(kind IN ('once','cron')),
 cron text, timezone text NOT NULL DEFAULT 'UTC', next_run_at timestamptz NOT NULL,
 enabled boolean NOT NULL DEFAULT true, template jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS task_schedules_due ON task_schedules(next_run_at) WHERE enabled;
CREATE TABLE IF NOT EXISTS task_triggers (
 id uuid PRIMARY KEY, name text NOT NULL, event_type text NOT NULL, filters jsonb NOT NULL DEFAULT '{}',
 enabled boolean NOT NULL DEFAULT true, template jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS task_trigger_events (
 id uuid PRIMARY KEY, source text NOT NULL, event_id text NOT NULL, event_type text NOT NULL,
 payload jsonb NOT NULL, processed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(source,event_id)
);
CREATE INDEX IF NOT EXISTS task_trigger_events_pending ON task_trigger_events(created_at) WHERE processed_at IS NULL;
