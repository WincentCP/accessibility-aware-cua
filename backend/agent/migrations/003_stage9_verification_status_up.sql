BEGIN;

ALTER TABLE IF EXISTS agent_steps
    DROP CONSTRAINT IF EXISTS agent_steps_verification_status_check;
ALTER TABLE IF EXISTS agent_steps
    ADD CONSTRAINT agent_steps_verification_status_check CHECK (
        verification_status IN ('UNVERIFIED', 'VERIFIED', 'FAILED', 'INCONCLUSIVE', 'UNCERTAIN', 'STALE')
    );

ALTER TABLE IF EXISTS verifications
    DROP CONSTRAINT IF EXISTS verifications_status_check;
ALTER TABLE IF EXISTS verifications
    ADD CONSTRAINT verifications_status_check CHECK (
        status IN ('UNVERIFIED', 'VERIFIED', 'FAILED', 'INCONCLUSIVE', 'UNCERTAIN', 'STALE')
    );

INSERT INTO schema_migrations (version) VALUES ('003_stage9_verification_status')
ON CONFLICT (version) DO NOTHING;

COMMIT;
