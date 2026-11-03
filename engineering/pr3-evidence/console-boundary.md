# Console boundary and compatibility gate

`services/console` is the canonical operator presentation boundary. `site/` remains public documentation. The `services/dashboard` compatibility shell was retired by [ADR-0090](../adr/0090-retire-dashboard-compatibility-shell.md); this evidence record is kept for its original gate.

1. `services/console` has an authenticated server-owned session and tenant context.
2. The console consumes the versioned API/SSE contracts through the server-only transport seam.
3. Four-role/two-tenant browser evidence passes, including no-fixture production assertions.
4. The operator origin has a rollback-capable artifact and the public docs origin remains independently available.
5. The owner records a cutover date and confirms the compatibility shell can be disabled without data or audit loss.

Until all five conditions are evidenced, no route in the compatibility shell may be described as a live Track D product surface and no fixture-backed route may be enabled in production.
