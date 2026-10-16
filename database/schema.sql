CREATE TABLE IF NOT EXISTS chats (
  id uuid PRIMARY KEY,
  title text NOT NULL DEFAULT 'New chat',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Private model input window plus completed-message watermark; transcript stays intact.
ALTER TABLE chats ADD COLUMN IF NOT EXISTS context_window jsonb;

CREATE TABLE IF NOT EXISTS messages (
  id uuid PRIMARY KEY,
  chat_id uuid NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  position bigint GENERATED ALWAYS AS IDENTITY,
  role text NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'assistant')),
  text text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS messages_chat_order ON messages(chat_id, position);

-- Upgrade existing local volumes as well as initializing new ones.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS reply_to_message_id uuid REFERENCES messages(id) ON DELETE CASCADE;
CREATE UNIQUE INDEX IF NOT EXISTS messages_one_reply ON messages(reply_to_message_id) WHERE reply_to_message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS attachments (
  id uuid PRIMARY KEY,
  message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  position integer NOT NULL,
  name text NOT NULL,
  size integer NOT NULL CHECK (size >= 0),
  content bytea NOT NULL
);

CREATE INDEX IF NOT EXISTS attachments_message_order ON attachments(message_id, position);

-- Generic MCP registration; credentials are environment references only.
CREATE TABLE IF NOT EXISTS mcp_servers (
  id uuid PRIMARY KEY,
  name varchar(100) NOT NULL,
  url varchar(2048) NOT NULL UNIQUE,
  auth_env_var varchar(128),
  tools jsonb NOT NULL DEFAULT '[]'::jsonb,
  allowed_tools text[] NOT NULL DEFAULT '{}',
  status varchar(20) NOT NULL DEFAULT 'unconnected' CHECK (status IN ('unconnected','connected','failed')),
  last_error text,
  discovered_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- RAG profiles reuse the generic MCP registry; no knowledge is stored here.
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS rest_url varchar(2048);
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS rest_status varchar(20) NOT NULL DEFAULT 'unconfigured';
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS rest_error text;
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS rag_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS agent_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS disconnected boolean NOT NULL DEFAULT false;
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS server_name varchar(200);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS tool_calls jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS description varchar(2000) NOT NULL DEFAULT '';
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS enabled boolean NOT NULL DEFAULT true;
-- Short-lived bounded confirmation/continuation; never bearer credentials.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS tool_state jsonb;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='mcp_servers_rest_status_check' AND conrelid='mcp_servers'::regclass) THEN
    ALTER TABLE mcp_servers ADD CONSTRAINT mcp_servers_rest_status_check CHECK (rest_status IN ('unconfigured','connected','failed','disconnected'));
  END IF;
END $$;

-- Durable task execution; same PostgreSQL database as conversations.
CREATE TABLE IF NOT EXISTS agent_tasks (
 id uuid PRIMARY KEY, conversation_id uuid NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
 message_id uuid REFERENCES messages(id) ON DELETE SET NULL, user_request text NOT NULL,
 goal text NOT NULL, plan jsonb NOT NULL DEFAULT '[]', criteria jsonb NOT NULL DEFAULT '[]',
 status varchar(24) NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','RUNNING','WAITING_APPROVAL','RETRYING','PAUSED','COMPLETED','FAILED','CANCELLED')),
 current_step integer NOT NULL DEFAULT 0, completed_steps jsonb NOT NULL DEFAULT '[]', progress integer NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
 next_action jsonb, result text, last_error text, retry_count integer NOT NULL DEFAULT 0,
 grants jsonb NOT NULL DEFAULT '[]', context_window jsonb, tokens_used bigint NOT NULL DEFAULT 0,
 estimated_cost_usd numeric(16,6) NOT NULL DEFAULT 0,
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

ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS estimated_cost_usd numeric(16,6) NOT NULL DEFAULT 0;

ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS context_state jsonb NOT NULL DEFAULT '{}';
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS prompt_tokens_start bigint NOT NULL DEFAULT 0;
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS prompt_turns_start integer NOT NULL DEFAULT 0;
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS prompt_active_start bigint NOT NULL DEFAULT 0;
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS continuation_count integer NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS task_integration_receipts (
 source TEXT NOT NULL,event_id UUID NOT NULL,fingerprint TEXT NOT NULL,
 task_id UUID NOT NULL REFERENCES agent_tasks(id),created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(source,event_id)
);
