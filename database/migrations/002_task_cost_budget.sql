ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS estimated_cost_usd numeric(16,6) NOT NULL DEFAULT 0;
