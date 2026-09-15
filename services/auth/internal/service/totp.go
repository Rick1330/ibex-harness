package service

import (
	"context"
	"errors"
	"fmt"
	"strings"
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
	ConfirmCiphertext(ctx context.Context, p repository.ConfirmCiphertextParams) error
}

// OrgID and UserID reduce primitive string coupling in TOTP APIs.
type OrgID string
type UserID string

// TenantRef identifies an org/user pair for attempt-gate operations.
type TenantRef struct {
	Org  OrgID
	User UserID
}

// KeyParts returns trimmed org/user strings for persistence keys.
func (r TenantRef) KeyParts() (string, string) {
	return strings.TrimSpace(string(r.Org)), strings.TrimSpace(string(r.User))
}

type totpAttemptGate interface {
	Allow(ref TenantRef) error
	Reset(ref TenantRef)
	Fail(ref TenantRef)
	// Release undoes a prior Allow reservation without clearing lockout state.
	Release(ref TenantRef)
}

// BeginEnrollmentParams scopes pending secret creation.
type BeginEnrollmentParams struct {
	OrgID       OrgID
	UserID      UserID
	AccountName string
}

// ConfirmEnrollmentParams scopes pending-secret confirmation.
type ConfirmEnrollmentParams struct {
	OrgID  OrgID
	UserID UserID
	Code   string
}

// CreateStepUpParams scopes TOTP verification and step-up JWT issuance.
type CreateStepUpParams struct {
	OrgID       OrgID
	UserID      UserID
	Code        string
	Permissions int64
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
func (s *TotpService) BeginEnrollment(ctx context.Context, p BeginEnrollmentParams) (string, error) {
	if err := s.requireReady(); err != nil {
		return "", err
	}
	orgID, userID := strings.TrimSpace(string(p.OrgID)), strings.TrimSpace(string(p.UserID))
	if orgID == "" || userID == "" {
		return "", ErrInvalidArgument
	}
	if err := s.ensureEnrollmentAllowed(ctx, orgID, userID); err != nil {
		return "", err
	}
	return s.createPendingSecret(ctx, orgID, userID, p.AccountName)
}

func (s *TotpService) createPendingSecret(ctx context.Context, orgID, userID, accountName string) (string, error) {
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
func (s *TotpService) ConfirmEnrollment(ctx context.Context, p ConfirmEnrollmentParams) error {
	ref := TenantRef{Org: p.OrgID, User: p.UserID}
	orgID, userID := ref.KeyParts()
	if err := s.attempts.Allow(ref); err != nil {
		return err
	}
	secret, row, err := s.loadPendingSecret(ctx, orgID, userID)
	if err != nil {
		s.attempts.Release(ref)
		return err
	}
	if !totp.Validate(strings.TrimSpace(p.Code), secret) {
		s.attempts.Fail(ref)
		return ErrTOTPInvalidCode
	}
	if err := s.repo.ConfirmCiphertext(ctx, repository.ConfirmCiphertextParams{
		OrgID: orgID, UserID: userID, Ciphertext: row.Ciphertext, At: time.Now().UTC(),
	}); err != nil {
		s.attempts.Release(ref)
		return err
	}
	s.attempts.Reset(ref)
	return nil
}

// CreateStepUp verifies TOTP for a confirmed enrollment and issues a step-up JWT.
func (s *TotpService) CreateStepUp(ctx context.Context, p CreateStepUpParams) (string, time.Time, error) {
	if !s.issuerOK {
		return "", time.Time{}, ErrSessionJWTMissing
	}
	ref := TenantRef{Org: p.OrgID, User: p.UserID}
	orgID, userID := ref.KeyParts()
	if err := s.attempts.Allow(ref); err != nil {
		return "", time.Time{}, err
	}
	if err := s.verifyConfirmedCode(ctx, p, ref); err != nil {
		if !errors.Is(err, ErrTOTPInvalidCode) {
			s.attempts.Release(ref)
		}
		return "", time.Time{}, err
	}
	s.attempts.Reset(ref)
	return s.issuer.IssueStepUp(sessionjwt.IssueStepUpParams{
		Subject: sessionjwt.Subject(userID), OrgID: sessionjwt.OrgID(orgID), Permissions: p.Permissions,
	})
}

func (s *TotpService) verifyConfirmedCode(ctx context.Context, p CreateStepUpParams, ref TenantRef) error {
	orgID, userID := ref.KeyParts()
	secret, err := s.loadSecret(ctx, orgID, userID)
	if err != nil {
		return err
	}
	row, err := s.repo.Get(ctx, orgID, userID)
	if err != nil {
		return mapTotpStoreErr(err)
	}
	if !row.ConfirmedAt.Valid {
		return ErrTOTPNotEnrolled
	}
	if !totp.Validate(strings.TrimSpace(p.Code), secret) {
		s.attempts.Fail(ref)
		return ErrTOTPInvalidCode
	}
	return nil
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

func (s *TotpService) requireReady() error {
	if !s.enabled {
		return ErrTOTPDisabled
	}
	if !s.ready {
		return ErrTOTPNotReady
	}
	return nil
}

func (s *TotpService) loadSecret(ctx context.Context, orgID, userID string) (string, error) {
	if err := s.requireReady(); err != nil {
		return "", err
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
