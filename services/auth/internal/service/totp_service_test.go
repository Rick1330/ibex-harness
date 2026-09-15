package service_test

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"database/sql"
	"encoding/base64"
	"encoding/pem"
	"errors"
	"sync"
	"testing"
	"time"

	ibexcrypto "github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
	"github.com/pquerna/otp/totp"
)

type memTOTPStore struct {
	mu     sync.Mutex
	rows   map[string]repository.TotpSecretRow
	master ibexcrypto.MasterKey
}

func (m *memTOTPStore) key(orgID, userID string) string { return orgID + ":" + userID }

func (m *memTOTPStore) UpsertPending(_ context.Context, row repository.TotpSecretRow) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.rows == nil {
		m.rows = map[string]repository.TotpSecretRow{}
	}
	row.ConfirmedAt = sql.NullTime{}
	m.rows[m.key(row.OrgID, row.UserID)] = row
	return nil
}

func (m *memTOTPStore) Get(_ context.Context, orgID, userID string) (repository.TotpSecretRow, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	row, ok := m.rows[m.key(orgID, userID)]
	if !ok {
		return repository.TotpSecretRow{}, repository.ErrTotpSecretNotFound
	}
	return row, nil
}

func (m *memTOTPStore) ConfirmCiphertext(_ context.Context, orgID, userID string, ciphertext []byte, at time.Time) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	key := m.key(orgID, userID)
	row, ok := m.rows[key]
	if !ok {
		return repository.ErrTotpSecretNotFound
	}
	if string(row.Ciphertext) != string(ciphertext) {
		return errors.New("ciphertext mismatch")
	}
	row.ConfirmedAt = sql.NullTime{Time: at, Valid: true}
	m.rows[key] = row
	return nil
}

func (m *memTOTPStore) plaintext(t *testing.T, orgID, userID string) string {
	t.Helper()
	row, err := m.Get(context.Background(), orgID, userID)
	if err != nil {
		t.Fatal(err)
	}
	plain, err := ibexcrypto.Open(m.master, ibexcrypto.SealedBlob{
		Ciphertext: row.Ciphertext, WrappedDEK: row.WrappedDEK, KeyID: row.EncryptionKeyID,
	})
	if err != nil {
		t.Fatal(err)
	}
	return string(plain)
}

func mustMasterEncoded(t *testing.T) (string, ibexcrypto.MasterKey) {
	t.Helper()
	raw := ibexcrypto.GenerateRandomBytes(ibexcrypto.MasterKeySize)
	enc := base64.StdEncoding.EncodeToString(raw)
	mk, err := ibexcrypto.ParseMasterKeyBase64(enc)
	if err != nil {
		t.Fatal(err)
	}
	return enc, mk
}

func mustIssuer(t *testing.T) *sessionjwt.Issuer {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	pemBytes := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(priv)})
	iss, err := sessionjwt.NewIssuer(string(pemBytes), "ibex-auth", "ibex-dashboard", time.Minute, time.Hour, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	return iss
}

func TestUnit_TotpService_EnrollmentConfirmAndStepUp(t *testing.T) {
	t.Parallel()
	enc, mk := mustMasterEncoded(t)
	store := &memTOTPStore{master: mk}
	svc, err := service.NewTotpService(store, service.MasterKeyConfig{Encoded: enc, KeyID: "v1"}, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	uri, err := svc.BeginEnrollment(context.Background(), "org-1", "user-1", "user-1@example.com")
	if err != nil || uri == "" {
		t.Fatalf("begin: uri=%q err=%v", uri, err)
	}
	secret := store.plaintext(t, "org-1", "user-1")
	code, err := totp.GenerateCode(secret, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	if err := svc.ConfirmEnrollment(context.Background(), "org-1", "user-1", code); err != nil {
		t.Fatalf("confirm: %v", err)
	}
	_, err = svc.BeginEnrollment(context.Background(), "org-1", "user-1", "again")
	if !errors.Is(err, service.ErrTOTPAlreadyDone) {
		t.Fatalf("want already done, got %v", err)
	}
	code2, err := totp.GenerateCode(secret, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	tok, exp, err := svc.CreateStepUp(context.Background(), "org-1", "user-1", code2, 7)
	if err != nil || tok == "" || exp.IsZero() {
		t.Fatalf("stepup tok=%q exp=%v err=%v", tok, exp, err)
	}
	if _, _, err := svc.CreateStepUp(context.Background(), "org-1", "user-1", "000000", 7); !errors.Is(err, service.ErrTOTPInvalidCode) {
		t.Fatalf("want invalid code, got %v", err)
	}
}

func TestUnit_TotpService_DisabledNotReadyAndGates(t *testing.T) {
	t.Parallel()
	store := &memTOTPStore{}
	disabled, err := service.NewTotpService(store, service.MasterKeyConfig{}, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := disabled.BeginEnrollment(context.Background(), "o", "u", "a"); !errors.Is(err, service.ErrTOTPDisabled) {
		t.Fatalf("disabled: %v", err)
	}
	notReady, err := service.NewTotpService(store, service.MasterKeyConfig{}, true, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := notReady.BeginEnrollment(context.Background(), "o", "u", "a"); !errors.Is(err, service.ErrTOTPNotReady) {
		t.Fatalf("not ready: %v", err)
	}
	if _, err := service.NewTotpService(nil, service.MasterKeyConfig{}, true, nil); err == nil {
		t.Fatal("expected nil repo error")
	}
	enc, _ := mustMasterEncoded(t)
	noJWT, err := service.NewTotpService(store, service.MasterKeyConfig{Encoded: enc}, true, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := noJWT.CreateStepUp(context.Background(), "o", "u", "123456", 1); !errors.Is(err, service.ErrSessionJWTMissing) {
		t.Fatalf("missing jwt: %v", err)
	}
	ready, err := service.NewTotpService(store, service.MasterKeyConfig{Encoded: enc}, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ready.BeginEnrollment(context.Background(), "", "u", "a"); !errors.Is(err, service.ErrInvalidArgument) {
		t.Fatalf("empty org: %v", err)
	}
	if _, _, err := ready.CreateStepUp(context.Background(), "o", "u", "123456", 1); !errors.Is(err, service.ErrTOTPNotEnrolled) {
		t.Fatalf("not enrolled: %v", err)
	}
}

func TestUnit_TotpAttempts_Lockout(t *testing.T) {
	t.Parallel()
	enc, mk := mustMasterEncoded(t)
	store := &memTOTPStore{master: mk}
	svc, err := service.NewTotpService(store, service.MasterKeyConfig{Encoded: enc, KeyID: "v1"}, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := svc.BeginEnrollment(context.Background(), "org", "user", "acct"); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 5; i++ {
		err := svc.ConfirmEnrollment(context.Background(), "org", "user", "000000")
		if !errors.Is(err, service.ErrTOTPInvalidCode) {
			t.Fatalf("attempt %d: %v", i, err)
		}
	}
	if err := svc.ConfirmEnrollment(context.Background(), "org", "user", "000000"); !errors.Is(err, service.ErrTOTPLockedOut) {
		t.Fatalf("want lockout, got %v", err)
	}
}
