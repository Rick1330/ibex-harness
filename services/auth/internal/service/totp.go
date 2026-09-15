package service

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	ibexcrypto "github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
	"github.com/pquerna/otp/totp"
)

var (
	// ErrTOTPDisabled is returned when IBEX_AUTH_TOTP_ENABLED is false.
	ErrTOTPDisabled = errors.New("totp disabled")
	// ErrTOTPNotReady is returned when the credentials master key is missing.
	ErrTOTPNotReady = errors.New("totp master key missing")
	// ErrTOTPInvalidCode is returned for a bad TOTP code.
	ErrTOTPInvalidCode = errors.New("invalid totp code")
	// ErrTOTPNotEnrolled is returned when no confirmed secret exists.
	ErrTOTPNotEnrolled = errors.New("totp not enrolled")
	// ErrTOTPAlreadyDone is returned when enrollment is already confirmed.
	ErrTOTPAlreadyDone = errors.New("totp already confirmed")
	// ErrTOTPLockedOut is returned after too many failed TOTP attempts.
	ErrTOTPLockedOut = errors.New("totp attempt limit exceeded")
	// ErrSessionJWTMissing is returned when step-up issuance needs RS256 but none is configured.
	ErrSessionJWTMissing = errors.New("session jwt issuer not configured")
)

const (
	totpMaxFailures = 5
	totpLockTTL     = 15 * time.Minute
)

// totpStore persists sealed TOTP secrets.
type totpStore interface {
	UpsertPending(ctx context.Context, row repository.TotpSecretRow) error
	Get(ctx context.Context, orgID, userID string) (repository.TotpSecretRow, error)
	ConfirmCiphertext(ctx context.Context, orgID, userID string, ciphertext []byte, at time.Time) error
}

type totpAttemptGate interface {
	Allow(orgID, userID string) error
	Reset(orgID, userID string)
	Fail(orgID, userID string)
}

// TotpService handles enrollment and step-up issuance.
type TotpService struct {
	repo     totpStore
	master   ibexcrypto.MasterKey
	keyID    string
	ready    bool
	enabled  bool
	issuer   *sessionjwt.Issuer
	issuerOK bool
	attempts totpAttemptGate
}

// NewTotpService constructs a TOTP service. enabled gates all RPCs.
func NewTotpService(repo totpStore, kek MasterKeyConfig, enabled bool, jwt *sessionjwt.Issuer) (*TotpService, error) {
	if repo == nil {
		return nil, fmt.Errorf("totp service: nil repo")
	}
	keyID := kek.KeyID
	if keyID == "" {
		keyID = "v1"
	}
	svc := &TotpService{
		repo: repo, keyID: keyID, enabled: enabled, issuer: jwt, issuerOK: jwt != nil,
		attempts: newMemoryTOTPAttempts(totpMaxFailures, totpLockTTL),
	}
	if strings.TrimSpace(kek.Encoded) == "" {
		return svc, nil
	}
	mk, err := ibexcrypto.ParseMasterKeyBase64(kek.Encoded)
	if err != nil {
		return nil, fmt.Errorf("totp service: %w", err)
	}
	svc.master = mk
	svc.ready = true
	return svc, nil
}

// WithAttemptGate replaces the in-memory TOTP attempt gate (Redis in production).
func (s *TotpService) WithAttemptGate(gate totpAttemptGate) *TotpService {
	if s == nil || gate == nil {
		return s
	}
	s.attempts = gate
	return s
}

// BeginEnrollment creates a pending sealed secret and returns an otpauth URI.
func (s *TotpService) BeginEnrollment(ctx context.Context, orgID, userID, accountName string) (string, error) {
	if !s.enabled {
		return "", ErrTOTPDisabled
	}
	if !s.ready {
		return "", ErrTOTPNotReady
	}
	orgID, userID = strings.TrimSpace(orgID), strings.TrimSpace(userID)
	if orgID == "" || userID == "" {
		return "", ErrInvalidArgument
	}
	if err := s.ensureEnrollmentAllowed(ctx, orgID, userID); err != nil {
		return "", err
	}
	key, err := totp.Generate(totp.GenerateOpts{
		Issuer:      "IBEX",
		AccountName: accountName,
	})
	if err != nil {
		return "", err
	}
	sealed, err := ibexcrypto.Seal(s.master, s.keyID, []byte(key.Secret()))
	if err != nil {
		return "", err
	}
	if err := s.repo.UpsertPending(ctx, repository.TotpSecretRow{
		OrgID: orgID, UserID: userID,
		Ciphertext: sealed.Ciphertext, WrappedDEK: sealed.WrappedDEK, EncryptionKeyID: sealed.KeyID,
	}); err != nil {
		return "", err
	}
	return key.URL(), nil
}

func (s *TotpService) ensureEnrollmentAllowed(ctx context.Context, orgID, userID string) error {
	existing, err := s.repo.Get(ctx, orgID, userID)
	if err == nil && existing.ConfirmedAt.Valid {
		return ErrTOTPAlreadyDone
	}
	if err != nil && !errors.Is(err, repository.ErrTotpSecretNotFound) {
		return err
	}
	return nil
}

// ConfirmEnrollment verifies a code against the pending secret.
func (s *TotpService) ConfirmEnrollment(ctx context.Context, orgID, userID, code string) error {
	if err := s.attempts.Allow(orgID, userID); err != nil {
		return err
	}
	secret, row, err := s.loadPendingSecret(ctx, orgID, userID)
	if err != nil {
		return err
	}
	if !totp.Validate(strings.TrimSpace(code), secret) {
		s.attempts.Fail(orgID, userID)
		return ErrTOTPInvalidCode
	}
	if err := s.repo.ConfirmCiphertext(ctx, orgID, userID, row.Ciphertext, time.Now().UTC()); err != nil {
		return err
	}
	s.attempts.Reset(orgID, userID)
	return nil
}

// CreateStepUp verifies TOTP for a confirmed enrollment and issues a step-up JWT.
func (s *TotpService) CreateStepUp(ctx context.Context, orgID, userID, code string, permissions int64) (string, time.Time, error) {
	if !s.issuerOK {
		return "", time.Time{}, ErrSessionJWTMissing
	}
	if err := s.attempts.Allow(orgID, userID); err != nil {
		return "", time.Time{}, err
	}
	secret, err := s.loadSecret(ctx, orgID, userID)
	if err != nil {
		return "", time.Time{}, err
	}
	row, err := s.repo.Get(ctx, orgID, userID)
	if err != nil {
		return "", time.Time{}, mapTotpStoreErr(err)
	}
	if !row.ConfirmedAt.Valid {
		return "", time.Time{}, ErrTOTPNotEnrolled
	}
	if !totp.Validate(strings.TrimSpace(code), secret) {
		s.attempts.Fail(orgID, userID)
		return "", time.Time{}, ErrTOTPInvalidCode
	}
	s.attempts.Reset(orgID, userID)
	return s.issuer.IssueStepUp(userID, orgID, permissions)
}

func (s *TotpService) loadPendingSecret(ctx context.Context, orgID, userID string) (string, repository.TotpSecretRow, error) {
	secret, err := s.loadSecret(ctx, orgID, userID)
	if err != nil {
		return "", repository.TotpSecretRow{}, err
	}
	row, err := s.repo.Get(ctx, orgID, userID)
	if err != nil {
		return "", repository.TotpSecretRow{}, mapTotpStoreErr(err)
	}
	if row.ConfirmedAt.Valid {
		return "", repository.TotpSecretRow{}, ErrTOTPAlreadyDone
	}
	return secret, row, nil
}

func (s *TotpService) loadSecret(ctx context.Context, orgID, userID string) (string, error) {
	if !s.enabled {
		return "", ErrTOTPDisabled
	}
	if !s.ready {
		return "", ErrTOTPNotReady
	}
	orgID, userID = strings.TrimSpace(orgID), strings.TrimSpace(userID)
	row, err := s.repo.Get(ctx, orgID, userID)
	if err != nil {
		return "", mapTotpStoreErr(err)
	}
	plain, err := ibexcrypto.Open(s.master, ibexcrypto.SealedBlob{
		Ciphertext: row.Ciphertext, WrappedDEK: row.WrappedDEK, KeyID: row.EncryptionKeyID,
	})
	if err != nil {
		return "", err
	}
	return string(plain), nil
}

func mapTotpStoreErr(err error) error {
	if errors.Is(err, repository.ErrTotpSecretNotFound) {
		return ErrTOTPNotEnrolled
	}
	return err
}

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

func totpAttemptKey(orgID, userID string) string {
	return strings.TrimSpace(orgID) + ":" + strings.TrimSpace(userID)
}

func (m *memoryTOTPAttempts) Allow(orgID, userID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	key := totpAttemptKey(orgID, userID)
	ent := m.entries[key]
	if !ent.lockedUntil.IsZero() && m.now().Before(ent.lockedUntil) {
		return ErrTOTPLockedOut
	}
	if !ent.lockedUntil.IsZero() && !m.now().Before(ent.lockedUntil) {
		delete(m.entries, key)
	}
	return nil
}

func (m *memoryTOTPAttempts) Fail(orgID, userID string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	key := totpAttemptKey(orgID, userID)
	ent := m.entries[key]
	ent.failures++
	if ent.failures >= m.maxFails {
		ent.lockedUntil = m.now().Add(m.lockTTL)
		ent.failures = 0
	}
	m.entries[key] = ent
}

func (m *memoryTOTPAttempts) Reset(orgID, userID string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.entries, totpAttemptKey(orgID, userID))
}
