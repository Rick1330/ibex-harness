package token_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

func TestUnit_Validator_MissPathPaysArgon2(t *testing.T) {
	t.Parallel()
	if testing.Short() {
		t.Skip("timing parity skipped in -short")
	}
	missV, wrongV, bearer := missAndWrongValidators(t)

	assertUnauthenticated(t, missV, bearer)
	assertUnauthenticated(t, wrongV, bearer)

	missDur, wrongDur := averageValidateDurations(t, missV, wrongV, bearer, 3)
	assertTimingParity(t, missDur, wrongDur)
}

func missAndWrongValidators(t *testing.T) (missV, wrongV *token.Validator, bearer string) {
	t.Helper()
	argon2 := token.TestArgon2Params()
	tokenID := uuid.New()
	bearer = "ibex_pat_" + tokenID.String() + "_secret"
	wrongHash, err := token.HashForTest(bearer+"_other", argon2)
	if err != nil {
		t.Fatal(err)
	}
	missV, err = token.NewValidator(&fakeLookup{err: sql.ErrNoRows}, argon2)
	if err != nil {
		t.Fatal(err)
	}
	wrongV, err = token.NewValidator(&fakeLookup{row: token.Row{Hash: wrongHash, OrgID: "org"}}, argon2)
	if err != nil {
		t.Fatal(err)
	}
	return missV, wrongV, bearer
}

func averageValidateDurations(t *testing.T, missV, wrongV *token.Validator, bearer string, samples int) (missDur, wrongDur time.Duration) {
	t.Helper()
	var missTotal, wrongTotal time.Duration
	for i := 0; i < samples; i++ {
		missTotal += timeValidate(t, missV, bearer)
		wrongTotal += timeValidate(t, wrongV, bearer)
	}
	return missTotal / time.Duration(samples), wrongTotal / time.Duration(samples)
}

func timeValidate(t *testing.T, v *token.Validator, bearer string) time.Duration {
	t.Helper()
	start := time.Now()
	assertUnauthenticated(t, v, bearer)
	return time.Since(start)
}

func assertUnauthenticated(t *testing.T, v *token.Validator, bearer string) {
	t.Helper()
	_, err := v.Validate(context.Background(), bearer)
	if !errors.Is(err, token.ErrUnauthenticated) {
		t.Fatalf("want ErrUnauthenticated, got %v", err)
	}
}

func assertTimingParity(t *testing.T, missDur, wrongDur time.Duration) {
	t.Helper()
	if wrongDur == 0 {
		t.Skip("wrong-secret duration too small to compare")
	}
	ratio := float64(missDur) / float64(wrongDur)
	if ratio < 0.25 || ratio > 4.0 {
		t.Fatalf("timing parity ratio=%.2f miss=%v wrong=%v (want roughly comparable)", ratio, missDur, wrongDur)
	}
	t.Logf("timing parity ratio=%.2f miss=%v wrong=%v", ratio, missDur, wrongDur)
}
