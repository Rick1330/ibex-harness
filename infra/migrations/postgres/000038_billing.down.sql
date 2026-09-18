DROP TRIGGER IF EXISTS budget_periods_updated_at ON ibex_billing.budget_periods;
DROP TRIGGER IF EXISTS rate_cards_updated_at ON ibex_billing.rate_cards;

DROP TABLE IF EXISTS ibex_billing.enforcement_decisions;
DROP TABLE IF EXISTS ibex_billing.budget_periods;
DROP TABLE IF EXISTS ibex_billing.rate_card_versions;
DROP TABLE IF EXISTS ibex_billing.rate_cards;

DROP SCHEMA IF EXISTS ibex_billing;
