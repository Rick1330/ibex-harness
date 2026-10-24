# Auth screens — design rationale

Login, signup, and TOTP enrollment sit outside the dense investigation shell.
`AuthShell` centers a single card (~420px) over a quiet atmospheric field
(radial ink + warm ochre glow, dotted mask). Brand lockup (`IX` + IBEX) is
the hero signal inside the card; page titles stay secondary.

## Honesty

- Generic credential errors; AuthUnavailable distinct from wrong password.
- Client login cooldown flagged as a gap vs TOTP-only server lockout.
- No forgot-password flow — contact admin.
- No backup-codes UI — endpoint absent in reviewed TOTP service.
- Step-up is an in-context modal; failures collapse to one non-leaking line.
- Signup creates an org-bound fixture session — not OIDC (ADR-0079 non-goal).

## Motion

`auth-card-enter` rise/fade, `auth-mark` scale-in, `auth-shell-glow` drift;
all respect `prefers-reduced-motion`.
