package bootstrap

import (
	"context"
	"database/sql"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// These tests prove the memory-service token path: `reconcileServiceToken` as an
// orchestrator, and `writeServiceToken` — the statement both it and
// `createIdentity` call — on its own.

func TestReconcileServiceTokenErrorPaths(t *testing.T) {
	bearer := mustPAT(t)
	orgID := uuid.New()
	tests := []struct {
		name string
		f    faultConfig
		want string
	}{
		{
			name: "lock fails",
			f:    faultConfig{query: errInjected},
			want: "lock organization for memory token",
		},
		{
			name: "organization is gone",
			f:    faultConfig{rows: []faultRow{lockRow(false)}},
			want: "missing or soft-deleted",
		},
		{
			name: "no owner",
			f: faultConfig{rows: []faultRow{
				lockRow(true), subjectsRow(nil, uuid.NewString()),
			}},
			want: "no active owner",
		},
		{
			name: "no agent",
			f: faultConfig{rows: []faultRow{
				lockRow(true), subjectsRow(uuid.NewString(), nil),
			}},
			want: "no active agent",
		},
		{
			name: "subject lookup fails",
			f: faultConfig{
				query: errInjected, queryAfter: 1, rows: []faultRow{lockRow(true)},
			},
			want: "look up owner and agent",
		},
		{
			name: "token write fails",
			f: faultConfig{
				query: errInjected, queryAfter: 2,
				rows: []faultRow{lockRow(true), subjectsRow(uuid.NewString(), uuid.NewString())},
			},
			want: "write memory service token",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			db := openFaultDB(t, tc.f)
			tx := beginFaultTx(t, db)
			err := reconcileServiceToken(context.Background(), tx, orgID, bearer)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("reconcileServiceToken error = %v, want %q", err, tc.want)
			}
		})
	}

	t.Run("success rebinds the managed row", func(t *testing.T) {
		db := openFaultDB(t, faultConfig{rows: []faultRow{
			lockRow(true),
			subjectsRow(uuid.NewString(), uuid.NewString()),
			serviceTokenRow(outcomeUpdated, uuid.NewString()),
		}})
		tx := beginFaultTx(t, db)
		if err := reconcileServiceToken(context.Background(), tx, orgID, bearer); err != nil {
			t.Fatalf("reconcileServiceToken: %v", err)
		}
	})
}

func TestServiceTokenHelperErrors(t *testing.T) {
	orgID := uuid.New()
	cases := []struct {
		name string
		f    faultConfig
		call func(context.Context, *sql.Tx) error
	}{
		{"query", faultConfig{query: errInjected}, func(ctx context.Context, tx *sql.Tx) error {
			return writeServiceToken(ctx, tx, serviceTokenInput{orgID: orgID, bearer: mustPAT(t)})
		}},
		{"scan", faultConfig{scan: true}, func(ctx context.Context, tx *sql.Tx) error {
			return writeServiceToken(ctx, tx, serviceTokenInput{orgID: orgID, bearer: mustPAT(t)})
		}},
		{"malformed token", faultConfig{}, func(ctx context.Context, tx *sql.Tx) error {
			return writeServiceToken(ctx, tx, serviceTokenInput{orgID: orgID, bearer: "not-a-pat"})
		}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			db := openFaultDB(t, tc.f)
			tx := beginFaultTx(t, db)
			if err := tc.call(context.Background(), tx); err == nil {
				t.Fatalf("%s returned no error", tc.name)
			}
		})
	}

	t.Run("inserted and updated are success", func(t *testing.T) {
		for _, outcome := range []string{outcomeInserted, outcomeUpdated} {
			db := openFaultDB(t, faultConfig{rows: []faultRow{
				serviceTokenRow(outcome, uuid.NewString()),
			}})
			tx := beginFaultTx(t, db)
			in := serviceTokenInput{orgID: orgID, bearer: mustPAT(t)}
			if err := writeServiceToken(context.Background(), tx, in); err != nil {
				t.Fatalf("%s outcome: %v", outcome, err)
			}
		}
	})
}
