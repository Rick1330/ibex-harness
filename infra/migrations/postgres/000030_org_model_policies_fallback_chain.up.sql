-- Milestone 4.C.4: opt-in fallback chain on org model policies (ADR-0077).
-- CHECK is NOT VALID so ADD skips a full-table scan; VALIDATE runs in 000031
-- (separate transaction) to avoid holding ACCESS EXCLUSIVE across validation.
ALTER TABLE ibex_core.org_model_policies
    ADD COLUMN fallback_chain TEXT[] NOT NULL DEFAULT '{}';

ALTER TABLE ibex_core.org_model_policies
    ADD CONSTRAINT org_model_policies_fallback_chain_len_check
    CHECK (cardinality(fallback_chain) <= 8) NOT VALID;
