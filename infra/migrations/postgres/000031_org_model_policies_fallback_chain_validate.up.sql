-- Milestone 4.C.4: validate fallback_chain cardinality CHECK (follow-up to 000030).
ALTER TABLE ibex_core.org_model_policies
    VALIDATE CONSTRAINT org_model_policies_fallback_chain_len_check;
