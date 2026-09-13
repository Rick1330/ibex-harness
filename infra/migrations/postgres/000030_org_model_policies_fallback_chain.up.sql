-- Milestone 4.C.4: opt-in fallback chain on org model policies (ADR-0077).
ALTER TABLE ibex_core.org_model_policies
    ADD COLUMN fallback_chain TEXT[] NOT NULL DEFAULT '{}';
