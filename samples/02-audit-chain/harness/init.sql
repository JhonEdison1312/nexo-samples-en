-- ADDED FOR THIS SAMPLE
-- nexo_admin is the docker-entrypoint superuser; nexo_app is the
-- unprivileged application role the tests connect as.
-- md5 password encryption so PgBouncer (plaintext userlist) can
-- authenticate to PostgreSQL 15+ which defaults to SCRAM-SHA-256.
SET password_encryption = 'md5';
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexo_app') THEN
        CREATE ROLE nexo_app LOGIN PASSWORD 'nexo_secret' NOSUPERUSER NOBYPASSRLS;
    END IF;
END
$$;
-- Database schema for HMAC Audit Chain demonstration
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

DROP TABLE IF EXISTS global_audit_logs CASCADE;
CREATE TABLE global_audit_logs (
    log_id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    school_id           UUID,
    performed_by_user_id UUID,
    action_type         VARCHAR(120) NOT NULL,
    entity_type         VARCHAR(120),
    entity_id           UUID,
    action_details      JSONB,
    ip_address          INET,
    user_agent          TEXT,
    chain_hash          TEXT,
    prev_audit_id       UUID,
    description         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Grant privileges to application user and set ownership so test can disable triggers
ALTER TABLE global_audit_logs OWNER TO nexo_app;
GRANT ALL PRIVILEGES ON global_audit_logs TO nexo_app;
