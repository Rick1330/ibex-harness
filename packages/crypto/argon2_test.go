package crypto

import (
	"strings"
	"testing"
	"time"
)

func TestHashSecretProductionPHC(t *testing.T) {
	hash, err := HashSecret("test-password", ProductionParams())
	if err != nil {
		t.Fatalf("hash: %v", err)
	}
	if !strings.HasPrefix(hash, ProductionPHCPrefix) {
		t.Fatalf("phc prefix: got %q", hash[:min(40, len(hash))])
	}
	ok, err := VerifySecret("test-password", hash, ProductionParams())
	if err != nil || !ok {
		t.Fatalf("verify ok: %v err: %v", ok, err)
	}
	ok, err = VerifySecret("wrong-password", hash, ProductionParams())
	if err != nil {
		t.Fatalf("wrong password err: %v", err)
	}
	if ok {
		t.Fatal("expected false for wrong password")
	}
}

func TestVerifySecretMalformedPHC(t *testing.T) {
	ok, err := VerifySecret("x", "not-a-phc", ProductionParams())
	if err == nil {
		t.Fatal("expected error for malformed phc")
	}
	if ok {
		t.Fatal("expected false ok")
	}
}

func TestHashTokenAlias(t *testing.T) {
	p := TestParams()
	h, err := HashToken("ibex_pat_test", p)
	if err != nil {
		t.Fatal(err)
	}
	ok, err := VerifyToken("ibex_pat_test", h, p)
	if err != nil || !ok {
		t.Fatalf("verify token: ok=%v err=%v", ok, err)
	}
}

func TestPHCVectorConsistency(t *testing.T) {
	// Self-consistency vector: fixed params produce verifiable PHC.
	p := TestParams()
	plain := "ibex-harness-crypto-vector-v1"
	h1, err := HashSecret(plain, p)
	if err != nil {
		t.Fatal(err)
	}
	ok, err := VerifySecret(plain, h1, p)
	if err != nil || !ok {
		t.Fatalf("round trip: ok=%v err=%v", ok, err)
	}
}

func TestVerifyTimingSmoke(t *testing.T) {
	if testing.Short() {
		t.Skip("timing smoke is advisory; skipped in -short")
	}
	p := TestParams()
	hash, err := HashSecret("test-password", p)
	if err != nil {
		t.Fatal(err)
	}
	start := time.Now()
	_, _ = VerifySecret("wrong", hash, p)
	wrongDuration := time.Since(start)
	start = time.Now()
	_, _ = VerifySecret("test-password", hash, p)
	correctDuration := time.Since(start)
	if correctDuration == 0 {
		t.Skip("correct duration too small to compare")
	}
	ratio := float64(wrongDuration) / float64(correctDuration)
	if ratio < 0.5 || ratio > 2.0 {
		t.Logf("advisory timing ratio=%.2f (wrong=%v correct=%v)", ratio, wrongDuration, correctDuration)
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
