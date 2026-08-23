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

// BenchmarkPrototypeWindow_ClientVisibleTTFBDelta counts feeds until first emit
// for near-passthrough holdback vs default 64. Modeled wall TTFT delta assumes
// 1 ms inter-chunk (reported as ns/ttfb_delta_model); CPU path stays sleep-free.
func BenchmarkPrototypeWindow_ClientVisibleTTFBDelta(b *testing.B) {
	const (
		chunk        = "tok " // 4 runes
		interChunkNS = int64(time.Millisecond)
		nearPass     = prototypeMaxPatternRunes
		defaultHB    = 64
	)
	b.ReportAllocs()
	b.ResetTimer()
	var feedDeltaSum int64
	for i := 0; i < b.N; i++ {
		passFeeds := feedsUntilFirstEmit(b, nearPass, chunk)
		holdFeeds := feedsUntilFirstEmit(b, defaultHB, chunk)
		feedDeltaSum += int64(holdFeeds - passFeeds)
	}
	avgFeedDelta := float64(feedDeltaSum) / float64(b.N)
	b.ReportMetric(avgFeedDelta, "feeds_until_emit_delta")
	b.ReportMetric(avgFeedDelta*float64(interChunkNS), "ns/ttfb_delta_model")
}

func feedsUntilFirstEmit(b *testing.B, holdback int, chunk string) int {
	b.Helper()
	w := mustBenchWindow(b, holdback)
	for n := 1; ; n++ {
		emit, err := w.Feed(chunk)
		if err != nil {
			b.Fatal(err)
		}
		if emit != "" {
			return n
		}
		if n > 1_000_000 {
			b.Fatal("first emit never arrived")
		}
	}
}

// BenchmarkPrototypeWindow_PerRequestMemory reports retained UTF-8 bytes per
// window at steady state (ASCII content → 1 byte/rune in the string buffer).
func BenchmarkPrototypeWindow_PerRequestMemory(b *testing.B) {
	holdback := 64
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		w := mustBenchWindow(b, holdback)
		if _, err := w.Feed(strings.Repeat("m", holdback+8)); err != nil {
			b.Fatal(err)
		}
		b.ReportMetric(float64(w.RetainedRunes()), "bytes_per_request")
	}
}

// BenchmarkPrototypeWindow_RetainedMemory reports aggregate retained runes for
// 100 concurrent windows (allocs/op for construct overhead).
func BenchmarkPrototypeWindow_RetainedMemory(b *testing.B) {
	const nWindows = 100
	holdback := 64
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		retained := 0
		for j := 0; j < nWindows; j++ {
			w := mustBenchWindow(b, holdback)
			if _, err := w.Feed(strings.Repeat("m", holdback+8)); err != nil {
				b.Fatal(err)
			}
			retained += w.RetainedRunes()
		}
		if retained != nWindows*holdback {
			b.Fatalf("retained=%d want=%d", retained, nWindows*holdback)
		}
		b.ReportMetric(float64(retained)/float64(nWindows), "runes_per_request")
	}
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
