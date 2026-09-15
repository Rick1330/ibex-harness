package service

import (
	"sync"
	"time"
)

type memoryTOTPAttempts struct {
	mu       sync.Mutex
	maxFails int
	lockTTL  time.Duration
	now      func() time.Time
	entries  map[string]totpAttemptEntry
}

type totpAttemptEntry struct {
	failures    int
	lockedUntil time.Time
}

func newMemoryTOTPAttempts(maxFails int, lockTTL time.Duration) *memoryTOTPAttempts {
	return &memoryTOTPAttempts{
		maxFails: maxFails, lockTTL: lockTTL, now: time.Now, entries: make(map[string]totpAttemptEntry),
	}
}

func totpAttemptKey(ref TenantRef) string {
	orgID, userID := ref.KeyParts()
	return orgID + ":" + userID
}

func (m *memoryTOTPAttempts) Allow(ref TenantRef) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	key := totpAttemptKey(ref)
	ent := m.entries[key]
	if !ent.lockedUntil.IsZero() && m.now().Before(ent.lockedUntil) {
		return ErrTOTPLockedOut
	}
	if !ent.lockedUntil.IsZero() && !m.now().Before(ent.lockedUntil) {
		delete(m.entries, key)
	}
	return nil
}

func (m *memoryTOTPAttempts) Fail(ref TenantRef) {
	m.mu.Lock()
	defer m.mu.Unlock()
	key := totpAttemptKey(ref)
	ent := m.entries[key]
	ent.failures++
	if ent.failures >= m.maxFails {
		ent.lockedUntil = m.now().Add(m.lockTTL)
		ent.failures = 0
	}
	m.entries[key] = ent
}

func (m *memoryTOTPAttempts) Release(ref TenantRef) {
	_ = ref
	// In-process gate does not pre-reserve on Allow; nothing to undo.
}

func (m *memoryTOTPAttempts) Reset(ref TenantRef) {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.entries, totpAttemptKey(ref))
}

var _ totpAttemptGate = (*memoryTOTPAttempts)(nil)
