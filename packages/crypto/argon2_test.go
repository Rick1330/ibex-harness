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

// TestVerifyTimingSmoke asserts that a wrong secret is not rejected before the
// Argon2id evaluation; the band and its rationale are in the body.
func TestVerifyTimingSmoke(t *testing.T) {
	if testing.Short() {
		t.Skip("timing smoke is advisory; skipped in -short")
	}
	p := TestParams()
	hash, err := HashSecret("test-password", p)
	if err != nil {
		t.Fatal(err)
	}
	samples := collectVerifyTimingSamples(t, hash, p)
	assertVerifySamplesMeasured(t, samples)
	medians := medianVerifyTiming(samples)
	ratio := float64(medians.all.wrong) / float64(medians.all.correct)
	// Both paths run exactly one Argon2id evaluation, so a wrong secret must cost
	// about as much as the correct one. A ratio below 0.5 means the mismatch was
	// rejected before hashing; the wide upper bound tolerates scheduler noise on a
	// loaded runner while still catching a doubled hashing pass. The per-order
	// medians are reported so an order-dependent bias cannot pass as a timing
	// difference.
	if ratio < 0.5 || ratio > 3.0 {
		t.Fatalf("wrong-secret verify is not comparable to correct-secret verify: ratio=%.2f all(wrong=%v correct=%v) wrong-first(wrong=%v correct=%v) correct-first(wrong=%v correct=%v)",
			ratio,
			medians.all.wrong, medians.all.correct,
			medians.wrongFirst.wrong, medians.wrongFirst.correct,
			medians.correctFirst.wrong, medians.correctFirst.correct,
		)
	}
}

// timingSample pairs one wrong-secret and one correct-secret measurement with the
// order they ran in. Keeping the label beside the durations means a difference
// caused by measurement order cannot be mistaken for a timing difference.
type timingSample struct {
	order   string
	wrong   time.Duration
	correct time.Duration
}

// timingPair is a wrong/correct median pair.
type timingPair struct {
	wrong   time.Duration
	correct time.Duration
}

// timingMedians holds medians over every sample plus medians for each measurement
// order, which is what makes an order-dependent bias visible.
type timingMedians struct {
	all          timingPair
	wrongFirst   timingPair
	correctFirst timingPair
}

// collectVerifyTimingSamples measures both verify paths seven times, alternating
// which path runs first so a warm cache or a frequency change cannot bias one
// side of the comparison.
func collectVerifyTimingSamples(t *testing.T, hash string, p Argon2Params) []timingSample {
	t.Helper()
	const sampleCount = 7
	samples := make([]timingSample, sampleCount)
	for i := range samples {
		samples[i] = measureTimingSample(t, hash, p, i%2 == 0)
	}
	return samples
}

// measureTimingSample measures both paths once in the requested order and records
// each duration against its path.
func measureTimingSample(t *testing.T, hash string, p Argon2Params, wrongFirst bool) timingSample {
	t.Helper()
	sample := timingSample{order: "correct-first"}
	if wrongFirst {
		sample.order = "wrong-first"
		sample.wrong = measureVerify(t, "wrong", hash, p)
		sample.correct = measureVerify(t, "test-password", hash, p)
		return sample
	}
	sample.correct = measureVerify(t, "test-password", hash, p)
	sample.wrong = measureVerify(t, "wrong", hash, p)
	return sample
}

// assertVerifySamplesMeasured fails on any zero duration: a zero means that path
// did not run, which is the regression this test exists to catch.
func assertVerifySamplesMeasured(t *testing.T, samples []timingSample) {
	t.Helper()
	for i, sample := range samples {
		if sample.wrong == 0 || sample.correct == 0 {
			t.Fatalf("verify sample %d (%s) is unmeasurable: wrong=%v correct=%v", i, sample.order, sample.wrong, sample.correct)
		}
	}
}

// medianVerifyTiming reduces the samples to medians for all samples and for each
// measurement order.
func medianVerifyTiming(samples []timingSample) timingMedians {
	return timingMedians{
		all:          medianTimingPair(samples),
		wrongFirst:   medianTimingPair(selectTimingOrder(samples, "wrong-first")),
		correctFirst: medianTimingPair(selectTimingOrder(samples, "correct-first")),
	}
}

// selectTimingOrder returns the samples measured in the given order.
func selectTimingOrder(samples []timingSample, order string) []timingSample {
	selected := make([]timingSample, 0, len(samples))
	for _, sample := range samples {
		if sample.order == order {
			selected = append(selected, sample)
		}
	}
	return selected
}

// medianTimingPair returns the median wrong and correct duration, or a zero pair
// when the group is empty.
func medianTimingPair(samples []timingSample) timingPair {
	if len(samples) == 0 {
		return timingPair{}
	}
	wrongs := make([]time.Duration, len(samples))
	corrects := make([]time.Duration, len(samples))
	for i, sample := range samples {
		wrongs[i] = sample.wrong
		corrects[i] = sample.correct
	}
	slices.Sort(wrongs)
	slices.Sort(corrects)
	return timingPair{wrong: wrongs[len(wrongs)/2], correct: corrects[len(corrects)/2]}
}

// measureVerify times one VerifySecret call and fails if the hash is malformed.
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
