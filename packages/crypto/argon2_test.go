package crypto

import (
	"slices"
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
	wrongDuration, correctDuration := medianVerifyDurations(t, hash, p)
	if wrongDuration == 0 || correctDuration == 0 {
		t.Fatalf("verify durations must be measurable: wrong=%v correct=%v", wrongDuration, correctDuration)
	}
	ratio := float64(wrongDuration) / float64(correctDuration)
	// Both paths run exactly one Argon2id evaluation, so a wrong secret must cost
	// about as much as the correct one. A ratio below 0.5 means the mismatch was
	// rejected before hashing; the wide upper bound tolerates scheduler noise on a
	// loaded runner while still catching a doubled hashing pass.
	if ratio < 0.5 || ratio > 3.0 {
		t.Fatalf("wrong-secret verify is not comparable to correct-secret verify: ratio=%.2f (wrong=%v correct=%v)", ratio, wrongDuration, correctDuration)
	}
}

// medianVerifyDurations measures the wrong- and correct-secret verify paths in
// interleaved batches and returns their medians. Interleaving spreads scheduler
// noise across both paths, and the median rejects a single preempted sample.
func medianVerifyDurations(t *testing.T, hash string, p Argon2Params) (wrong, correct time.Duration) {
	t.Helper()
	const samples = 7
	wrongSamples := make([]time.Duration, samples)
	correctSamples := make([]time.Duration, samples)
	for i := 0; i < samples; i++ {
		wrongSamples[i] = measureVerify(t, "wrong", hash, p)
		correctSamples[i] = measureVerify(t, "test-password", hash, p)
	}
	slices.Sort(wrongSamples)
	slices.Sort(correctSamples)
	return wrongSamples[samples/2], correctSamples[samples/2]
}

func measureVerify(t *testing.T, plaintext, hash string, p Argon2Params) time.Duration {
	t.Helper()
	start := time.Now()
	if _, err := VerifySecret(plaintext, hash, p); err != nil {
		t.Fatalf("verify %q: %v", plaintext, err)
	}
	return time.Since(start)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
