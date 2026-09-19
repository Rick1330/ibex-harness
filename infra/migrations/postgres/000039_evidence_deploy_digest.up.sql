-- Milestone 4.P.5: record deployed image digest on evidence runs (extend evidence.v1; no new type).
ALTER TABLE ibex_core.evidence_runs
    ADD COLUMN IF NOT EXISTS deploy_image_digest TEXT;

COMMENT ON COLUMN ibex_core.evidence_runs.deploy_image_digest IS
    'OCI image digest of the service build that produced this run (4.P.5 supply-chain).';
