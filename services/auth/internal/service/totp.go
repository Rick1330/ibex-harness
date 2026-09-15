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
	// ErrSessionJWTMissing is returned when step-up issuance needs RS256 but none is configured.
	ErrSessionJWTMissing = errors.New("session jwt issuer not configured")
)

// totpStore persists sealed TOTP secrets.
type totpStore interface {
	UpsertPending(ctx context.Context, row repository.TotpSecretRow) error
	Get(ctx context.Context, orgID, userID string) (repository.TotpSecretRow, error)
	Confirm(ctx context.Context, orgID, userID string, at time.Time) error
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
	svc := &TotpService{repo: repo, keyID: keyID, enabled: enabled, issuer: jwt, issuerOK: jwt != nil}
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
	if existing, err := s.repo.Get(ctx, orgID, userID); err == nil && existing.ConfirmedAt.Valid {
		return "", ErrTOTPAlreadyDone
	} else if err != nil && !errors.Is(err, repository.ErrTotpSecretNotFound) {
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

// ConfirmEnrollment verifies a code against the pending secret.
func (s *TotpService) ConfirmEnrollment(ctx context.Context, orgID, userID, code string) error {
	secret, err := s.loadSecret(ctx, orgID, userID)
	if err != nil {
		return err
	}
	row, err := s.repo.Get(ctx, orgID, userID)
	if err != nil {
		return mapTotpStoreErr(err)
	}
	if row.ConfirmedAt.Valid {
		return ErrTOTPAlreadyDone
	}
	if !totp.Validate(strings.TrimSpace(code), secret) {
		return ErrTOTPInvalidCode
	}
	return s.repo.Confirm(ctx, orgID, userID, time.Now().UTC())
}

// CreateStepUp verifies TOTP for a confirmed enrollment and issues a step-up JWT.
func (s *TotpService) CreateStepUp(ctx context.Context, orgID, userID, code string, permissions int64) (string, time.Time, error) {
	if !s.issuerOK {
		return "", time.Time{}, ErrSessionJWTMissing
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
		return "", time.Time{}, ErrTOTPInvalidCode
	}
	return s.issuer.IssueStepUp(userID, orgID, permissions)
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
