CREATE SCHEMA ibex_core;

CREATE OR REPLACE FUNCTION ibex_core.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
