-- Restrict ibex_app to INSERT-only on failed_tasks (ADR-0062 operator forensics).
REVOKE SELECT ON ibex_core.failed_tasks FROM ibex_app;
