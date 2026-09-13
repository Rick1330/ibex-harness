-- Milestone 4.C.4: drop fallback_chain (reverse of 000030 up).
ALTER TABLE ibex_core.org_model_policies
    DROP CONSTRAINT IF EXISTS org_model_policies_fallback_chain_len_check;

ALTER TABLE ibex_core.org_model_policies
    DROP COLUMN IF EXISTS fallback_chain;
