package http

import (
	"strings"
	"testing"
	"time"
)

func mustBenchWindow(b *testing.B, holdback int) *PrototypeWindowBuffer {
	b.Helper()
	w, err := NewPrototypeWindowBuffer(PrototypeWindowConfig{
		HoldbackRunes: holdback, MaxBufferRunes: 1 << 20,
	})
	if err != nil {
		b.Fatal(err)
	}
	return w
}

func primeUntilEmit(b *testing.B, w *PrototypeWindowBuffer, chunk string) {
	b.Helper()
	for {
		emit, err := w.Feed(chunk)
		if err != nil {
			b.Fatal(err)
		}
		if emit != "" {
			return
		}
	}
}

func feedOrReset(b *testing.B, w **PrototypeWindowBuffer, chunk string, holdback int) {
	b.Helper()
	if _, err := (*w).Feed(chunk); err == nil {
		return
	}
	*w = mustBenchWindow(b, holdback)
}

// BenchmarkPrototypeWindow_FirstEmit measures time until the first non-empty emit
// (proxy for added TTFT from holdback).
func BenchmarkPrototypeWindow_FirstEmit(b *testing.B) {
	for _, holdback := range []int{16, 64, 256} {
		b.Run(holdbackName(holdback), func(b *testing.B) {
			runFirstEmitBench(b, holdback)
		})
	}
}

func runFirstEmitBench(b *testing.B, holdback int) {
	chunk := "token "
	b.ReportAllocs()
	b.ResetTimer()
	var firstEmitNs int64
	for i := 0; i < b.N; i++ {
		w := mustBenchWindow(b, holdback)
		start := time.Now()
		primeUntilEmit(b, w, chunk)
		firstEmitNs += time.Since(start).Nanoseconds()
	}
	b.ReportMetric(float64(firstEmitNs)/float64(b.N), "ns/first_emit")
}

// BenchmarkPrototypeWindow_FeedSteady measures steady-state Feed after first emit.
func BenchmarkPrototypeWindow_FeedSteady(b *testing.B) {
	chunk := strings.Repeat("a", 32)
	for _, holdback := range []int{prototypeMaxPatternRunes, 64, 256} {
		b.Run(holdbackName(holdback), func(b *testing.B) {
			runFeedSteadyBench(b, holdback, chunk)
		})
	}
}

func runFeedSteadyBench(b *testing.B, holdback int, chunk string) {
	w := mustBenchWindow(b, holdback)
	primeUntilEmit(b, w, chunk)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		feedOrReset(b, &w, chunk, holdback)
	}
}

// BenchmarkPrototypeWindow_RetainedMemory reports retained runes at steady state.
func BenchmarkPrototypeWindow_RetainedMemory(b *testing.B) {
	const nWindows = 100
	holdback := 64
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		retained := fillWindowsRetained(b, nWindows, holdback)
		if retained != nWindows*holdback {
			b.Fatalf("retained=%d want=%d", retained, nWindows*holdback)
		}
		b.ReportMetric(float64(retained), "runes_retained")
	}
}

func fillWindowsRetained(b *testing.B, nWindows, holdback int) int {
	b.Helper()
	windows := make([]*PrototypeWindowBuffer, nWindows)
	for j := 0; j < nWindows; j++ {
		w := mustBenchWindow(b, holdback)
		if _, err := w.Feed(strings.Repeat("m", holdback+8)); err != nil {
			b.Fatal(err)
		}
		windows[j] = w
	}
	var retained int
	for _, w := range windows {
		retained += w.RetainedRunes()
	}
	return retained
}

// BenchmarkPrototypeWindow_BackpressureProxy shows holdback Feed alone stays
// well under the ADR-0027 50ms backpressure threshold.
func BenchmarkPrototypeWindow_BackpressureProxy(b *testing.B) {
	const backpressureThreshold = 50 * time.Millisecond
	w := mustBenchWindow(b, 64)
	chunk := strings.Repeat("z", 80)
	b.ReportAllocs()
	b.ResetTimer()
	var maxFeedNs int64
	for i := 0; i < b.N; i++ {
		start := time.Now()
		feedOrReset(b, &w, chunk, 64)
		elapsed := time.Since(start)
		if ns := elapsed.Nanoseconds(); ns > maxFeedNs {
			maxFeedNs = ns
		}
		if elapsed >= backpressureThreshold {
			b.Fatalf("holdback Feed alone took %v (>= backpressure threshold)", elapsed)
		}
	}
	b.ReportMetric(float64(maxFeedNs), "ns/max_feed")
}

func holdbackName(n int) string {
	switch n {
	case 14:
		return "holdback14"
	case 16:
		return "holdback16"
	case 64:
		return "holdback64"
	case 256:
		return "holdback256"
	default:
		return "holdback"
	}
}
