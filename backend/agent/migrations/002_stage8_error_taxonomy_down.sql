BEGIN;

DO $$
DECLARE
    table_name text;
    constraint_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['task_runs', 'agent_steps', 'verifications']
    LOOP
        IF to_regclass('public.' || table_name) IS NOT NULL THEN
            constraint_name := table_name || '_error_code_check';
            EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', table_name, constraint_name);
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I CHECK (error_code IN (' ||
                '''NONE'', ''INVALID_ACTION'', ''TARGET_NOT_FOUND'', ''STALE_OBSERVATION'', ' ||
                '''EXECUTION_FAILED'', ''VERIFICATION_FAILED'', ''APPROVAL_REQUIRED'', ' ||
                '''USER_TAKEOVER'', ''MAX_STEPS_REACHED'', ''INTERNAL_ERROR''))',
                table_name,
                constraint_name
            );
        END IF;
    END LOOP;
END $$;

DO $$
BEGIN
    IF to_regclass('public.schema_migrations') IS NOT NULL THEN
        DELETE FROM schema_migrations WHERE version = '002_stage8_error_taxonomy';
    END IF;
END $$;

COMMIT;
