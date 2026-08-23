package http

import (
	"strings"
	"testing"
	"time"
)

// BenchmarkPrototypeWindow_FirstEmit measures time until the first non-empty emit
// (proxy for added TTFT from holdback). Holdback delays first client bytes until
// retained runes exceed HoldbackRunes.
func BenchmarkPrototypeWindow_FirstEmit(b *testing.B) {
	for _, holdback := range []int{16, 64, 256} {
		if holdback < prototypeMaxPatternRunes {
			holdback = prototypeMaxPatternRunes
		}
		b.Run(holdbackName(holdback), func(b *testing.B) {
			chunk := "token "
			b.ReportAllocs()
			b.ResetTimer()
			var firstEmitNs int64
			for i := 0; i < b.N; i++ {
				w, err := NewPrototypeWindowBuffer(PrototypeWindowConfig{
					HoldbackRunes: holdback, MaxBufferRunes: 1 << 20,
				})
				if err != nil {
					b.Fatal(err)
				}
				start := time.Now()
				var got string
				for got == "" {
					got, err = w.Feed(chunk)
					if err != nil {
						b.Fatal(err)
					}
				}
				firstEmitNs += time.Since(start).Nanoseconds()
			}
			b.ReportMetric(float64(firstEmitNs)/float64(b.N), "ns/first_emit")
		})
	}
}

// BenchmarkPrototypeWindow_PassthroughVsHoldback compares steady-state Feed cost
// with holdback vs an immediate-flush path (holdback equal to max pattern floor).
func BenchmarkPrototypeWindow_FeedSteady(b *testing.B) {
	chunk := strings.Repeat("a", 32)
	for _, holdback := range []int{prototypeMaxPatternRunes, 64, 256} {
		b.Run(holdbackName(holdback), func(b *testing.B) {
			w, err := NewPrototypeWindowBuffer(PrototypeWindowConfig{
				HoldbackRunes: holdback, MaxBufferRunes: 1 << 20,
			})
			if err != nil {
				b.Fatal(err)
			}
			// Prime past first emit so we measure steady Feed.
			for {
				emit, err := w.Feed(chunk)
				if err != nil {
					b.Fatal(err)
				}
				if emit != "" {
					break
				}
			}
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				if _, err := w.Feed(chunk); err != nil {
					// Reset on overflow to keep bench running.
					w, err = NewPrototypeWindowBuffer(PrototypeWindowConfig{
						HoldbackRunes: holdback, MaxBufferRunes: 1 << 20,
					})
					if err != nil {
						b.Fatal(err)
					}
				}
			}
		})
	}
}

// BenchmarkPrototypeWindow_RetainedMemory reports retained runes at steady state
// for concurrent-ish sequential windows (allocs/op stands in for per-request overhead).
func BenchmarkPrototypeWindow_RetainedMemory(b *testing.B) {
	const nWindows = 100
	holdback := 64
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		windows := make([]*PrototypeWindowBuffer, nWindows)
		for j := 0; j < nWindows; j++ {
			w, err := NewPrototypeWindowBuffer(PrototypeWindowConfig{HoldbackRunes: holdback})
			if err != nil {
				b.Fatal(err)
			}
			if _, err := w.Feed(strings.Repeat("m", holdback+8)); err != nil {
				b.Fatal(err)
			}
			windows[j] = w
		}
		var retained int
		for _, w := range windows {
			retained += w.RetainedRunes()
		}
		if retained != nWindows*holdback {
			b.Fatalf("retained=%d want=%d", retained, nWindows*holdback)
		}
		b.ReportMetric(float64(retained), "runes_retained")
	}
}

// BenchmarkPrototypeWindow_BackpressureProxy shows holdback Feed alone stays
// well under the ADR-0027 50ms backpressure threshold; slow client flush is a
// separate signal (not invented by buffering).
func BenchmarkPrototypeWindow_BackpressureProxy(b *testing.B) {
	const backpressureThreshold = 50 * time.Millisecond
	w, err := NewPrototypeWindowBuffer(PrototypeWindowConfig{HoldbackRunes: 64})
	if err != nil {
		b.Fatal(err)
	}
	chunk := strings.Repeat("z", 80)
	b.ReportAllocs()
	b.ResetTimer()
	var maxFeedNs int64
	for i := 0; i < b.N; i++ {
		start := time.Now()
		_, err := w.Feed(chunk)
		elapsed := time.Since(start)
		if err != nil {
			w, _ = NewPrototypeWindowBuffer(PrototypeWindowConfig{HoldbackRunes: 64})
			continue
		}
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
