-- Shared trigger function for updated_at maintenance.
-- This migration is idempotent because `set_updated_at()` already exists
-- from `000001_init_schemas`; we still `CREATE OR REPLACE` to keep
-- milestone sequencing self-contained.
CREATE OR REPLACE FUNCTION ibex_core.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

