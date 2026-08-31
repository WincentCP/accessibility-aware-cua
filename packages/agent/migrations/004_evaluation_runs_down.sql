BEGIN;
DROP TABLE IF EXISTS evaluation_runs;
DELETE FROM schema_migrations WHERE version = '004_evaluation_runs';
COMMIT;
