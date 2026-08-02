package token_test

import (
	"context"
	"database/sql"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

// TestValidator_MissPathPaysArgon2 ensures prefix misses burn Argon2 similarly to wrong-secret hits.
func TestValidator_MissPathPaysArgon2(t *testing.T) {
	t.Parallel()
	if testing.Short() {
		t.Skip("timing parity skipped in -short")
	}
	argon2 := token.TestArgon2Params()
	tokenID := uuid.New()
	bearer := "ibex_pat_" + tokenID.String() + "_secret"
	wrongHash, err := token.HashForTest(bearer+"_other", argon2)
	if err != nil {
		t.Fatal(err)
	}

	missLookup := &fakeLookup{err: sql.ErrNoRows}
	wrongLookup := &fakeLookup{row: token.Row{Hash: wrongHash, OrgID: "org"}}

	missV, err := token.NewValidator(missLookup, argon2)
	if err != nil {
		t.Fatal(err)
	}
	wrongV, err := token.NewValidator(wrongLookup, argon2)
	if err != nil {
		t.Fatal(err)
	}

	// Warm up so first-call allocator noise does not dominate.
	_, _ = missV.Validate(context.Background(), bearer)
	_, _ = wrongV.Validate(context.Background(), bearer)

	const samples = 3
	var missTotal, wrongTotal time.Duration
	for i := 0; i < samples; i++ {
		start := time.Now()
		_, _ = missV.Validate(context.Background(), bearer)
		missTotal += time.Since(start)

		start = time.Now()
		_, _ = wrongV.Validate(context.Background(), bearer)
		wrongTotal += time.Since(start)
	}
	missDur := missTotal / samples
	wrongDur := wrongTotal / samples
	if wrongDur == 0 {
		t.Skip("wrong-secret duration too small to compare")
	}
	ratio := float64(missDur) / float64(wrongDur)
	if ratio < 0.25 || ratio > 4.0 {
		t.Fatalf("timing parity ratio=%.2f miss=%v wrong=%v (want roughly comparable)", ratio, missDur, wrongDur)
	}
	t.Logf("timing parity ratio=%.2f miss=%v wrong=%v", ratio, missDur, wrongDur)
}
