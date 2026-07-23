package authcache

import (
	"sync"

	"github.com/bits-and-blooms/bloom/v3"
)

// bloomFilter is a two-generation invalid-token bloom guarded by mu.
// When the active generation reaches BloomExpectedItems adds, it is demoted
// to previous and replaced so the false-positive rate stays bounded.
type bloomFilter struct {
	mu       sync.RWMutex
	active   *bloom.BloomFilter
	previous *bloom.BloomFilter
	adds     uint
	expected uint
	fpRate   float64
}

func newBloomFilter(expected uint, fpRate float64) *bloomFilter {
	// OR of two generations ≈ 2p; size each generation for p/2 to keep combined FP near cfg.
	return &bloomFilter{
		active:   bloom.NewWithEstimates(expected, halfFPRate(fpRate)),
		expected: expected,
		fpRate:   halfFPRate(fpRate),
	}
}

func halfFPRate(fpRate float64) float64 {
	half := fpRate / 2
	if half <= 0 || half >= 1 {
		return fpRate
	}
	return half
}

func (b *bloomFilter) test(hash digest) bool {
	b.mu.RLock()
	defer b.mu.RUnlock()
	if b.active.TestString(string(hash)) {
		return true
	}
	return b.previous != nil && b.previous.TestString(string(hash))
}

func (b *bloomFilter) add(hash digest) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.active.AddString(string(hash))
	b.adds++
	if b.adds < b.expected {
		return
	}
	b.previous = b.active
	b.active = bloom.NewWithEstimates(b.expected, b.fpRate)
	b.adds = 0
}
