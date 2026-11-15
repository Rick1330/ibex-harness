package main

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/config"
)

const (
	// authCapabilityLogin is the login the auth service must connect as. It is
	// compiled in on purpose: POSTGRES_DSN already names the login, and a second
	// configurable source would let the check below be reconfigured to match a
	// mistake.
	authCapabilityLogin = "ibex_auth"
	// ownerLogin is the migration owner. Every service must stay off it: the
	// tenancy guarantee rests on the connection not being able to bypass RLS.
	ownerLogin = "ibex"
	// loginVerifyTimeout bounds the startup check so a wedged database fails
	// startup instead of hanging it.
	loginVerifyTimeout = 5 * time.Second
)

// capabilityLoginSQL reports the effective and session logins plus whether
// either is a superuser. COALESCE(..., true) fails closed: a login that cannot
// be resolved in pg_roles is treated as privileged.
const capabilityLoginSQL = `
	SELECT current_user, session_user,
	       COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), true),
	       COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = session_user), true)`

// openVerifiedAuthPostgres opens the pool and refuses to hand it back unless the
// connection assumed the ibex_auth capability login. A wrong password already
// fails loudly at connect; a wrong login starts silently and re-enables the RLS
// bypass the tenancy guarantee rests on, so it fails startup instead.
func openVerifiedAuthPostgres(cfg config.Config) (*sql.DB, error) {
	db, err := openAuthPostgres(cfg)
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), loginVerifyTimeout)
	defer cancel()
	if err := verifyAuthDBLogin(ctx, db); err != nil {
		_ = db.Close() // best-effort close: the pool is unusable after a failed check
		return nil, err
	}
	return db, nil
}

// verifyAuthDBLogin is the startup assertion. It is a variable only so the
// shutdown test can start the process without a database; production never
// reassigns it.
var verifyAuthDBLogin = assertAuthCapabilityLogin

// assertAuthCapabilityLogin refuses to run unless the connection is the
// ibex_auth capability login and neither the owner nor a superuser. It runs
// once at startup, never per request, and never echoes the DSN.
func assertAuthCapabilityLogin(ctx context.Context, db *sql.DB) error {
	var current, session string
	var currentSuper, sessionSuper bool
	if err := db.QueryRowContext(ctx, capabilityLoginSQL).
		Scan(&current, &session, &currentSuper, &sessionSuper); err != nil {
		return fmt.Errorf("auth: verify login role: %w", err)
	}
	if current == ownerLogin || session == ownerLogin {
		return fmt.Errorf(
			"auth: connection login is %q, the owner login; auth must connect as the %q capability login, never the RLS-bypassing owner",
			ownerLogin, authCapabilityLogin,
		)
	}
	if currentSuper || sessionSuper {
		return fmt.Errorf(
			"auth: connection login %q (current_user %q) is a superuser; auth must connect as the non-superuser %q capability login",
			session, current, authCapabilityLogin,
		)
	}
	if current != authCapabilityLogin {
		return fmt.Errorf(
			"auth: connection login is %q, want the %q capability login; POSTGRES_DSN names the login and the expected value is compiled in",
			current, authCapabilityLogin,
		)
	}
	return nil
}
