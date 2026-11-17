package bootstrap

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"
)

// These tests prove the entrypoints: that a failure at any database boundary is
// propagated by `bootstrap`/`bootstrapInTx`, and that the second-organization
// guard runs before anything is written. The driver and row fixtures they use
// are in bootstrap_fault_harness_test.go.

func TestBootstrapErrorPropagation(t *testing.T) {
	cfg := testConfig(t)

	closed, err := sql.Open("ibex-fault", "")
	if err != nil {
		t.Fatalf("open fault db: %v", err)
	}
	_ = closed.Close()
	if _, err := bootstrap(context.Background(), closed, cfg); err == nil {
		t.Fatal("bootstrap on a closed handle returned no error")
	}

	tests := []struct {
		name string
		f    faultConfig
		want string
	}{
		{
			name: "commit fails",
			f:    faultConfig{commit: errInjected, rows: firstRunRows()},
			want: "commit bootstrap transaction",
		},
		{
			name: "inventory read fails",
			f:    faultConfig{query: errInjected},
			want: "list organizations",
		},
		{
			name: "organization read fails",
			f:    faultConfig{query: errInjected, queryAfter: 1, rows: firstRunRows()},
			want: "insert organization",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			db := openFaultDB(t, tc.f)
			_, err := bootstrap(context.Background(), db, cfg)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("bootstrap error = %v, want %q", err, tc.want)
			}
		})
	}
}

func TestBootstrapInTxPropagatesOrganizationFailure(t *testing.T) {
	// queryAfter 1 skips the inventory read so the organization statement is the
	// one that fails.
	db := openFaultDB(t, faultConfig{query: errInjected, queryAfter: 1, rows: firstRunRows()})
	tx := beginFaultTx(t, db)
	_, err := bootstrapInTx(context.Background(), tx, testConfig(t))
	if err == nil || !strings.Contains(err.Error(), "insert organization") {
		t.Fatalf("bootstrapInTx error = %v, want an insert-organization failure", err)
	}
	if !errors.Is(err, errInjected) {
		t.Fatalf("bootstrapInTx error = %v, want the injected fault in its chain", err)
	}
}

// TestGuardSecondOrganization covers P2-13: a rerun with a different slug on an
// installation that already has one must not mint a second owner credential.
func TestGuardSecondOrganization(t *testing.T) {
	tests := []struct {
		name    string
		cfg     bootstrapConfig
		rows    []faultRow
		wantErr string
	}{
		{
			name: "fresh installation is allowed",
			cfg:  testConfig(t),
			rows: []faultRow{emptyInventoryRow()},
		},
		{
			name: "the existing slug is allowed",
			cfg:  testConfig(t),
			rows: []faultRow{inventoryRow("fault-injection")},
		},
		{
			name: "a different slug is refused",
			cfg:  testConfig(t),
			rows: []faultRow{inventoryRow("ibex")},
			wantErr: `refusing to create organization "fault-injection": this ` +
				`installation already has organization "ibex"`,
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			tx := beginFaultTx(t, openFaultDB(t, faultConfig{rows: tc.rows}))
			err := guardSecondOrganization(context.Background(), tx, tc.cfg)
			if tc.wantErr == "" {
				if err != nil {
					t.Fatalf("guard refused an allowed case: %v", err)
				}
				return
			}
			if err == nil || !strings.Contains(err.Error(), tc.wantErr) {
				t.Fatalf("guard error = %v, want %q", err, tc.wantErr)
			}
		})
	}
}

func TestDescribeSlugs(t *testing.T) {
	if got := describeSlugs([]string{"ibex"}); got != `organization "ibex"` {
		t.Fatalf("describeSlugs(one) = %q", got)
	}
	if got := describeSlugs([]string{"alpha", "ibex"}); got != `organizations "alpha", "ibex"` {
		t.Fatalf("describeSlugs(two) = %q", got)
	}
}

// TestGuardSecondOrganizationAllowFlag proves the only way past the refusal is
// the explicit operator statement.
func TestGuardSecondOrganizationAllowFlag(t *testing.T) {
	cfg := testConfig(t)
	cfg.AllowSecondOrg = true
	tx := beginFaultTx(t, openFaultDB(t, faultConfig{rows: []faultRow{inventoryRow("ibex")}}))
	if err := guardSecondOrganization(context.Background(), tx, cfg); err != nil {
		t.Fatalf("guard refused with IBEX_BOOTSTRAP_ALLOW_SECOND_ORG=true: %v", err)
	}
}

// TestBootstrapInTxRefusesSecondOrganization is the same refusal through the
// entrypoint the command uses, so a future reordering of bootstrapInTx that
// skipped the guard would fail here.
func TestBootstrapInTxRefusesSecondOrganization(t *testing.T) {
	db := openFaultDB(t, faultConfig{rows: []faultRow{inventoryRow("ibex")}})
	tx := beginFaultTx(t, db)
	_, err := bootstrapInTx(context.Background(), tx, testConfig(t))
	if err == nil || !strings.Contains(err.Error(), "IBEX_BOOTSTRAP_ALLOW_SECOND_ORG=true") {
		t.Fatalf("bootstrapInTx error = %v, want a second-organization refusal", err)
	}
	if execCalls != 0 {
		t.Fatalf("refused run performed %d writes, want none", execCalls)
	}
}
