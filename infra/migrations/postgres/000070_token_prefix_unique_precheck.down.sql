-- 000070 prechecks only; it changes no state. The rollback for this pair is
-- 000071's down, which drops the unique index.
SELECT 1;
