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
                '''NONE'', ''INVALID_ACTION'', ''TARGET_NOT_FOUND'', ''AMBIGUOUS_TARGET'', ' ||
                '''STALE_OBSERVATION'', ''TARGET_DISABLED'', ''TARGET_NOT_VISIBLE'', ' ||
                '''TARGET_NOT_EDITABLE'', ''ACTION_TIMEOUT'', ''NAVIGATION_INTERRUPTED'', ' ||
                '''POLICY_BLOCKED'', ''UNSUPPORTED_ACTION'', ''EXECUTION_FAILED'', ' ||
                '''VERIFICATION_FAILED'', ''APPROVAL_REQUIRED'', ''USER_TAKEOVER'', ' ||
                '''MAX_STEPS_REACHED'', ''INTERNAL_ERROR''))',
                table_name,
                constraint_name
            );
        END IF;
    END LOOP;
END $$;

INSERT INTO schema_migrations (version) VALUES ('002_stage8_error_taxonomy')
ON CONFLICT (version) DO NOTHING;

COMMIT;
