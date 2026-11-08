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
-- Schema and seed data for RLS + PgBouncer demonstration
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Helper functions matching NEXO schema (sql/schema.sql lines 1322-1345)
CREATE OR REPLACE FUNCTION get_current_school_id()
RETURNS UUID AS $$
DECLARE v_school_id TEXT;
BEGIN
    v_school_id := current_setting('app.current_school_id', true);
    IF v_school_id IS NULL OR v_school_id = '' THEN RETURN NULL; END IF;
    RETURN v_school_id::UUID;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

CREATE OR REPLACE FUNCTION get_current_role()
RETURNS TEXT AS $$
DECLARE v_role TEXT;
BEGIN
    v_role := current_setting('app.current_role', true);
    IF v_role IS NULL OR v_role = '' THEN RETURN NULL; END IF;
    RETURN v_role;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- Schools table
DROP TABLE IF EXISTS schools CASCADE;
CREATE TABLE schools (
    school_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    school_name TEXT NOT NULL
);

-- Students table
DROP TABLE IF EXISTS students CASCADE;
CREATE TABLE students (
    student_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    school_id UUID NOT NULL REFERENCES schools(school_id),
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL
);

-- Seed schools
INSERT INTO schools (school_id, school_name) VALUES
    ('11111111-1111-1111-1111-111111111111', 'Oakwood High School'),
    ('22222222-2222-2222-2222-222222222222', 'Pinecrest Academy');

-- Seed students (2 per school)
INSERT INTO students (school_id, first_name, last_name) VALUES
    ('11111111-1111-1111-1111-111111111111', 'Alice', 'Smith'),
    ('11111111-1111-1111-1111-111111111111', 'Bob', 'Jones'),
    ('22222222-2222-2222-2222-222222222222', 'Charlie', 'Brown'),
    ('22222222-2222-2222-2222-222222222222', 'Diana', 'Prince');

-- RLS policies are applied by src/rls_policies.sql (loaded by make up / compose mount)

-- Grant access to application user
GRANT ALL PRIVILEGES ON schools TO nexo_app;
GRANT ALL PRIVILEGES ON students TO nexo_app;
