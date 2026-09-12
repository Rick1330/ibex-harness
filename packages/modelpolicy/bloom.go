package modelpolicy

import (
	"sync"

	"github.com/bits-and-blooms/bloom/v3"
)

// policyBloom tracks org IDs that may have policy rows (positive hint).
// False positives only cause an LRU/DB check; misses always load from source.
type policyBloom struct {
	mu       sync.RWMutex
	active   *bloom.BloomFilter
	previous *bloom.BloomFilter
	adds     uint
	expected uint
	fpRate   float64
}

func newPolicyBloom(expected uint, fpRate float64) *policyBloom {
	half := fpRate / 2
	if half <= 0 || half >= 1 {
		half = fpRate
	}
	return &policyBloom{
		active:   bloom.NewWithEstimates(expected, half),
		expected: expected,
		fpRate:   half,
	}
}

func (b *policyBloom) mayHave(orgKey string) bool {
	b.mu.RLock()
	defer b.mu.RUnlock()
	if b.active.TestString(orgKey) {
		return true
	}
	return b.previous != nil && b.previous.TestString(orgKey)
}

func (b *policyBloom) add(orgKey string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.active.AddString(orgKey)
	b.adds++
	if b.adds < b.expected {
		return
	}
	b.previous = b.active
	b.active = bloom.NewWithEstimates(b.expected, b.fpRate)
	b.adds = 0
}

func (b *policyBloom) clear() {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.active = bloom.NewWithEstimates(b.expected, b.fpRate)
	b.previous = nil
	b.adds = 0
}
