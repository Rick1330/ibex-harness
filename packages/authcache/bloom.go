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
	return &bloomFilter{
		active:   bloom.NewWithEstimates(expected, fpRate),
		expected: expected,
		fpRate:   fpRate,
	}
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
