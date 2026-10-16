ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS context_state jsonb NOT NULL DEFAULT '{}';
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS prompt_tokens_start bigint NOT NULL DEFAULT 0;
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS prompt_turns_start integer NOT NULL DEFAULT 0;
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS prompt_active_start bigint NOT NULL DEFAULT 0;
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS continuation_count integer NOT NULL DEFAULT 0;
