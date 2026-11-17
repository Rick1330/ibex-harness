package bootstrap

import (
	"context"
	"database/sql"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// These tests prove the identity path: `createIdentity` as an orchestrator, and
// the two statements it writes (`insertIdentity`, `insertToken`) on their own.

func TestCreateIdentityErrorPaths(t *testing.T) {
	cfg := testConfig(t)
	tests := []struct {
		name string
		f    faultConfig
		want string
	}{
		{
			name: "identity insert",
			f:    faultConfig{query: errInjected},
			want: "insert owner user and default agent",
		},
		{
			name: "identity scan",
			f:    faultConfig{scan: true},
			want: "insert owner user and default agent",
		},
		{
			name: "bootstrap PAT insert",
			f:    faultConfig{exec: errInjected, rows: []faultRow{identityRow()}},
			want: "insert bootstrap PAT",
		},
		{
			name: "memory token write fails",
			f:    faultConfig{query: errInjected, queryAfter: 1, rows: []faultRow{identityRow()}},
			want: "write memory service token",
		},
		{
			name: "memory token prefix is taken",
			f: faultConfig{rows: []faultRow{
				identityRow(), serviceTokenRow(outcomePrefixConflict, ""),
			}},
			want: "already bound to another organization",
		},
		{
			name: "memory token is revoked",
			f: faultConfig{rows: []faultRow{
				identityRow(), serviceTokenRow(outcomeRevokedRefused, uuid.NewString()),
			}},
			want: "revoked",
		},
		{
			name: "memory token outcome is unknown",
			f: faultConfig{rows: []faultRow{
				identityRow(), serviceTokenRow("sideways", uuid.NewString()),
			}},
			want: "unrecognised outcome",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			db := openFaultDB(t, tc.f)
			tx := beginFaultTx(t, db)
			_, err := createIdentity(context.Background(), tx, cfg, uuid.New())
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("createIdentity error = %v, want %q", err, tc.want)
			}
		})
	}

	t.Run("success writes the memory token", func(t *testing.T) {
		db := openFaultDB(t, faultConfig{rows: []faultRow{
			identityRow(), serviceTokenRow(outcomeInserted, uuid.NewString()),
		}})
		tx := beginFaultTx(t, db)
		result, err := createIdentity(context.Background(), tx, cfg, uuid.New())
		if err != nil {
			t.Fatalf("createIdentity: %v", err)
		}
		if !result.MemoryTokenManaged || result.PAT == "" {
			t.Fatalf("result = %+v", result)
		}
	})
}

func TestIdentityHelperErrors(t *testing.T) {
	cfg := testConfig(t)
	orgID := uuid.New()
	cases := []struct {
		name string
		f    faultConfig
		call func(context.Context, *sql.Tx) error
	}{
		{"identity insert", faultConfig{query: errInjected}, func(ctx context.Context, tx *sql.Tx) error {
			_, _, err := insertIdentity(ctx, tx, identityInput{orgID: orgID, cfg: cfg})
			return err
		}},
		{"bootstrap PAT insert", faultConfig{exec: errInjected}, func(ctx context.Context, tx *sql.Tx) error {
			in := tokenInput{orgID: orgID, userID: uuid.New(), agentID: uuid.New(), name: cfg.PATName}
			_, err := insertToken(ctx, tx, in)
			return err
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
}
