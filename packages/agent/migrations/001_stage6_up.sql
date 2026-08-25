BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id uuid PRIMARY KEY,
    thread_id text NOT NULL UNIQUE,
    input_modality text NOT NULL CHECK (input_modality IN ('text', 'voice_transcript')),
    started_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz
);

CREATE TABLE IF NOT EXISTS messages (
    message_id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('USER', 'AGENT', 'SYSTEM')),
    content text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS experiment_configs (
    config_hash text PRIMARY KEY,
    model_id text NOT NULL,
    prompt_hash text NOT NULL,
    browser_version text NOT NULL,
    seed integer NOT NULL CHECK (seed >= 0),
    config_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS task_runs (
    run_id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    task_id text NOT NULL CHECK (task_id ~ '^T(0[1-9]|1[0-2])$'),
    condition_id text NOT NULL CHECK (condition_id IN ('C0', 'C1', 'C2')),
    config_hash text NOT NULL REFERENCES experiment_configs(config_hash),
    model_id text NOT NULL,
    prompt_hash text NOT NULL,
    browser_version text NOT NULL,
    seed integer NOT NULL CHECK (seed >= 0),
    goal_payload jsonb NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    success boolean,
    terminal_reason text CHECK (terminal_reason IN ('COMPLETED', 'USER_STOP', 'MAX_STEPS', 'SAFETY_STOP', 'ERROR')),
    error_code text NOT NULL DEFAULT 'NONE' CHECK (error_code IN (
        'NONE', 'INVALID_ACTION', 'TARGET_NOT_FOUND', 'STALE_OBSERVATION',
        'EXECUTION_FAILED', 'VERIFICATION_FAILED', 'APPROVAL_REQUIRED',
        'USER_TAKEOVER', 'MAX_STEPS_REACHED', 'INTERNAL_ERROR'
    )),
    duration_ms integer CHECK (duration_ms >= 0),
    step_count integer NOT NULL DEFAULT 0 CHECK (step_count >= 0),
    recovery_count integer NOT NULL DEFAULT 0 CHECK (recovery_count >= 0),
    intervention_count integer NOT NULL DEFAULT 0 CHECK (intervention_count >= 0)
);

CREATE TABLE IF NOT EXISTS agent_steps (
    step_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES task_runs(run_id) ON DELETE CASCADE,
    step_index integer NOT NULL CHECK (step_index >= 0),
    before_observation_ref uuid NOT NULL,
    after_observation_ref uuid,
    observation_version integer NOT NULL CHECK (observation_version >= 1),
    action_type text NOT NULL CHECK (action_type IN (
        'navigate', 'click', 'type', 'select', 'check', 'uncheck', 'press',
        'scroll', 'wait', 'back', 'ask_user', 'handoff', 'stop'
    )),
    action_payload jsonb NOT NULL,
    verification_status text NOT NULL CHECK (verification_status IN (
        'UNVERIFIED', 'VERIFIED', 'FAILED', 'INCONCLUSIVE', 'STALE'
    )),
    risk_level text NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    latency_ms integer NOT NULL CHECK (latency_ms >= 0),
    error_code text NOT NULL DEFAULT 'NONE' CHECK (error_code IN (
        'NONE', 'INVALID_ACTION', 'TARGET_NOT_FOUND', 'STALE_OBSERVATION',
        'EXECUTION_FAILED', 'VERIFICATION_FAILED', 'APPROVAL_REQUIRED',
        'USER_TAKEOVER', 'MAX_STEPS_REACHED', 'INTERNAL_ERROR'
    )),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, step_index)
);

CREATE TABLE IF NOT EXISTS verifications (
    verification_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES task_runs(run_id) ON DELETE CASCADE,
    step_id uuid NOT NULL REFERENCES agent_steps(step_id) ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('UNVERIFIED', 'VERIFIED', 'FAILED', 'INCONCLUSIVE', 'STALE')),
    evidence jsonb NOT NULL,
    before_observation_ref uuid NOT NULL,
    after_observation_ref uuid,
    error_code text NOT NULL DEFAULT 'NONE' CHECK (error_code IN (
        'NONE', 'INVALID_ACTION', 'TARGET_NOT_FOUND', 'STALE_OBSERVATION',
        'EXECUTION_FAILED', 'VERIFICATION_FAILED', 'APPROVAL_REQUIRED',
        'USER_TAKEOVER', 'MAX_STEPS_REACHED', 'INTERNAL_ERROR'
    )),
    checked_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS task_map_snapshots (
    snapshot_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES task_runs(run_id) ON DELETE CASCADE,
    version integer NOT NULL CHECK (version >= 1),
    observation_version integer NOT NULL CHECK (observation_version >= 1),
    snapshot_payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, version)
);

CREATE TABLE IF NOT EXISTS focus_handoffs (
    handoff_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES task_runs(run_id) ON DELETE CASCADE,
    step_id uuid REFERENCES agent_steps(step_id) ON DELETE SET NULL,
    status text NOT NULL CHECK (status IN ('NONE', 'REQUESTED', 'ACTIVE', 'RESUMING', 'COMPLETED')),
    target_ref text,
    announcement text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS interventions (
    intervention_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES task_runs(run_id) ON DELETE CASCADE,
    step_id uuid REFERENCES agent_steps(step_id) ON DELETE SET NULL,
    kind text NOT NULL CHECK (kind IN ('APPROVAL', 'TAKEOVER', 'CLARIFICATION', 'CANCEL')),
    status text NOT NULL CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'COMPLETED')),
    reason text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_task_runs_metrics
    ON task_runs (task_id, condition_id, success, completed_at);
CREATE INDEX IF NOT EXISTS idx_agent_steps_run ON agent_steps (run_id, step_index);
CREATE INDEX IF NOT EXISTS idx_interventions_pending
    ON interventions (run_id, status) WHERE status = 'PENDING';

INSERT INTO schema_migrations (version) VALUES ('001_stage6')
ON CONFLICT (version) DO NOTHING;

COMMIT;
