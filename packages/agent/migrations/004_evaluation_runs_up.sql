BEGIN;

CREATE TABLE IF NOT EXISTS evaluation_runs (
    manifest_run_id text NOT NULL,
    attempt integer NOT NULL CHECK (attempt >= 1),
    split text NOT NULL CHECK (split IN ('pilot', 'final')),
    task_id text NOT NULL CHECK (task_id ~ '^(T(0[1-9]|1[0-2])|P0[1-4])$'),
    condition_id text NOT NULL CHECK (condition_id IN ('C0', 'C1', 'C2')),
    configuration text NOT NULL CHECK (configuration IN ('B0', 'B1', 'P')),
    pair_id text NOT NULL,
    seed integer NOT NULL CHECK (seed >= 0),
    config_hash text NOT NULL,
    failure_class text NOT NULL CHECK (failure_class IN ('NONE', 'AGENT', 'INFRASTRUCTURE')),
    oracle_success boolean,
    result_payload jsonb NOT NULL,
    completed_at timestamptz NOT NULL,
    PRIMARY KEY (manifest_run_id, attempt)
);

CREATE INDEX IF NOT EXISTS idx_evaluation_runs_analysis
    ON evaluation_runs (split, configuration, condition_id, oracle_success);

INSERT INTO schema_migrations (version) VALUES ('004_evaluation_runs')
ON CONFLICT (version) DO NOTHING;

COMMIT;
