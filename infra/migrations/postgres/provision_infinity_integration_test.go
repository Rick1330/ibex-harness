//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"strings"
	"testing"
	"time"
)

// roleAttributeCase is one `VALID UNTIL` spelling and the role state it must
// produce.
type roleAttributeCase struct {
	name        string
	alter       string
	wantExpired bool
	wantDescr   string
}

// roleAttributeCases covers the three shapes lib/pq can hand back: the two
// infinity sentinels as text, and a finite timestamp in a non-UTC offset.
//
// The offset in the third case is in the INPUT, which PostgreSQL normalises to
// an instant; what the reader renders depends on the session TimeZone. The
// fixture pins that TimeZone away from UTC, so this case fails if the
// `AT TIME ZONE 'UTC'` in roleValidUntilSQL is dropped: a server west of UTC
// would then render 2031-02-02T21:05:06 and an expired role could parse as
// unexpired.
func roleAttributeCases() []roleAttributeCase {
	return []roleAttributeCase{
		{
			name:      "infinity",
			alter:     `ALTER ROLE ibex_provision_infinity_probe VALID UNTIL 'infinity'`,
			wantDescr: "validuntil=infinity",
		},
		{
			name:        "negative infinity",
			alter:       `ALTER ROLE ibex_provision_infinity_probe VALID UNTIL '-infinity'`,
			wantExpired: true,
			wantDescr:   "validuntil=-infinity",
		},
		{
			name:      "finite in a non-utc offset",
			alter:     `ALTER ROLE ibex_provision_infinity_probe VALID UNTIL '2031-02-03 04:05:06.789012+02'`,
			wantDescr: "validuntil=2031-02-03T02:05:06Z",
		},
	}
}

// check applies the case's `VALID UNTIL`, reloads the probe role, and asserts
// the three derived states the provisioner relies on. It lives outside the test
// function so the table body stays a single call and the case logic stays
// readable on its own.
func (tc roleAttributeCase) check(t *testing.T, ctx context.Context, tx *sql.Tx) {
	t.Helper()
	if _, err := tx.ExecContext(ctx, tc.alter); err != nil {
		t.Fatalf("alter probe role: %v", err)
	}
	attributes, err := loadRoleAttributes(tx, provisionTarget{role: "ibex_provision_infinity_probe"})
	if err != nil {
		t.Fatalf("loadRoleAttributes: %v", err)
	}
	if got := attributes.expired(time.Now()); got != tc.wantExpired {
		t.Fatalf("expired = %v, want %v", got, tc.wantExpired)
	}
	if !strings.Contains(attributes.describe(), tc.wantDescr) {
		t.Fatalf("describe = %q, want it to contain %q", attributes.describe(), tc.wantDescr)
	}
	// The two non-expiring states pass the safe-role postcondition; an
	// expired credential must fail it.
	if got := attributes.safe(time.Now()); got == tc.wantExpired {
		t.Fatalf("safe = %v with expired = %v", got, tc.wantExpired)
	}
}

// TestLoadRoleAttributesReadsExpirySentinels is the database half of the
// infinity fix: lib/pq hands `rolvaliduntil = 'infinity'` back as text, so the
// old sql.NullTime scan failed with "unsupported Scan, storing driver.Value
// type []uint8 into type *time.Time", and a role an operator had given
// `VALID UNTIL 'infinity'` could never be provisioned.
//
// The probe role is created and altered inside a transaction that is always
// rolled back, because `VALID UNTIL` can only be set by ALTER ROLE and the role
// must not outlive the test. Every statement is a compile-time literal: no role
// name or timestamp is formatted into SQL.
func TestLoadRoleAttributesReadsExpirySentinels(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()

	tx, err := f.db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("begin probe transaction: %v", err)
	}
	defer func() { _ = tx.Rollback() }()

	// NOINHERIT and CONNECTION LIMIT -1 are the two attributes the safe-role
	// postcondition also asserts, so only the expiry decides these cases.
	if _, err := tx.ExecContext(ctx,
		`CREATE ROLE ibex_provision_infinity_probe LOGIN NOINHERIT CONNECTION LIMIT -1`); err != nil {
		t.Fatalf("create probe role: %v", err)
	}

	// Pin the session TimeZone away from UTC for the probe transaction. Without
	// it the fixture runs at UTC, where to_char(rolvaliduntil) and
	// to_char(rolvaliduntil AT TIME ZONE 'UTC') render the same text and the
	// finite case cannot detect the normalisation being removed.
	if _, err := tx.ExecContext(ctx, `SET LOCAL TimeZone = 'America/New_York'`); err != nil {
		t.Fatalf("pin probe TimeZone: %v", err)
	}

	for _, tc := range roleAttributeCases() {
		t.Run(tc.name, func(t *testing.T) { tc.check(t, ctx, tx) })
	}
}
