-- Milestone 4.P.1 decision 9: ibex_app must not be superuser or bypass RLS.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ibex_app') THEN
        ALTER ROLE ibex_app NOSUPERUSER NOBYPASSRLS;
    ELSE
        CREATE ROLE ibex_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END
$$;
