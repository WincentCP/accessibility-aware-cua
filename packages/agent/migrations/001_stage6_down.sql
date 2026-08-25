BEGIN;

DROP TABLE IF EXISTS interventions;
DROP TABLE IF EXISTS focus_handoffs;
DROP TABLE IF EXISTS task_map_snapshots;
DROP TABLE IF EXISTS verifications;
DROP TABLE IF EXISTS agent_steps;
DROP TABLE IF EXISTS task_runs;
DROP TABLE IF EXISTS experiment_configs;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS schema_migrations;

COMMIT;
