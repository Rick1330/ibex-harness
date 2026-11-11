//go:build integration

package postgres

import (
	"strings"
	"testing"
	"time"
)

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

	tests := []struct {
		name        string
		alter       string
		wantExpired bool
		wantDescr   string
	}{
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
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
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
		})
	}
}
