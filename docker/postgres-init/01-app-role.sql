-- Phase 16 Task 3: least-privilege app role for real RLS verification.
-- Runs automatically on first `docker compose up` (fresh volume only).
-- The bootstrap superuser (agentready) owns objects; the app connects as
-- agentready_app, which can never bypass RLS the way a superuser/owner can.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentready_app') THEN
        CREATE ROLE agentready_app WITH LOGIN PASSWORD 'agentready_app_dev'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE agentready TO agentready_app;
GRANT USAGE ON SCHEMA public TO agentready_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agentready_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agentready_app;
