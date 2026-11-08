-- Validate the cascade added in 000060 in its own migration.
--
-- Single statement, and in its own file, for lock scope: VALIDATE takes SHARE
-- UPDATE EXCLUSIVE and scans concurrently with writes, and because 000060
-- committed its own transaction its ACCESS EXCLUSIVE lock is already released.
ALTER TABLE ibex_core.idempotency_ledger
    VALIDATE CONSTRAINT idempotency_ledger_agent_id_fkey;
