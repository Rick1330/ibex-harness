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
	"github.com/alicebob/miniredis/v2"
	"github.com/pquerna/otp/totp"
	"github.com/redis/go-redis/v9"
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

func (m *memTOTPStore) ConfirmCiphertext(_ context.Context, p repository.ConfirmCiphertextParams) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	key := m.key(p.OrgID, p.UserID)
	row, ok := m.rows[key]
	if !ok {
		return repository.ErrTotpSecretNotFound
	}
	if len(p.Ciphertext) > 0 && string(row.Ciphertext) != string(p.Ciphertext) {
		return errors.New("ciphertext mismatch")
	}
	row.ConfirmedAt = sql.NullTime{Time: p.At, Valid: true}
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
	iss, err := sessionjwt.NewIssuer(sessionjwt.IssuerConfig{
		PrivateKeyPEM: string(pemBytes),
		Issuer:        "ibex-auth",
		Audience:      "ibex-dashboard",
		AccessTTL:     time.Minute,
		RefreshTTL:    time.Hour,
		StepUpTTL:     time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	return iss
}

func beginP(org, user, acct string) service.BeginEnrollmentParams {
	return service.BeginEnrollmentParams{OrgID: service.OrgID(org), UserID: service.UserID(user), AccountName: acct}
}

func confirmP(org, user, code string) service.ConfirmEnrollmentParams {
	return service.ConfirmEnrollmentParams{OrgID: service.OrgID(org), UserID: service.UserID(user), Code: code}
}

func stepUpP(org, user, code string, perms int64) service.CreateStepUpParams {
	return service.CreateStepUpParams{OrgID: service.OrgID(org), UserID: service.UserID(user), Code: code, Permissions: perms}
}

func TestUnit_TotpService_EnrollmentConfirmAndStepUp(t *testing.T) {
	t.Parallel()
	enc, mk := mustMasterEncoded(t)
	store := &memTOTPStore{master: mk}
	svc, err := service.NewTotpService(store, service.MasterKeyConfig{Encoded: enc, KeyID: "v1"}, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	uri, err := svc.BeginEnrollment(context.Background(), beginP("org-1", "user-1", "user-1@example.com"))
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	if uri == "" {
		t.Fatal("begin: empty uri")
	}
	secret := store.plaintext(t, "org-1", "user-1")
	code, err := totp.GenerateCode(secret, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	if err := svc.ConfirmEnrollment(context.Background(), confirmP("org-1", "user-1", code)); err != nil {
		t.Fatalf("confirm: %v", err)
	}
	_, err = svc.BeginEnrollment(context.Background(), beginP("org-1", "user-1", "again"))
	if !errors.Is(err, service.ErrTOTPAlreadyDone) {
		t.Fatalf("want already done, got %v", err)
	}
	assertStepUpOK(t, svc, secret)
}

func assertStepUpOK(t *testing.T, svc *service.TotpService, secret string) {
	t.Helper()
	code, err := totp.GenerateCode(secret, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	tok, exp, err := svc.CreateStepUp(context.Background(), stepUpP("org-1", "user-1", code, 7))
	if err != nil {
		t.Fatalf("stepup: %v", err)
	}
	if tok == "" || exp.IsZero() {
		t.Fatalf("stepup tok=%q exp=%v", tok, exp)
	}
	_, _, err = svc.CreateStepUp(context.Background(), stepUpP("org-1", "user-1", "000000", 7))
	if !errors.Is(err, service.ErrTOTPInvalidCode) {
		t.Fatalf("want invalid code, got %v", err)
	}
}

func TestUnit_TotpService_Disabled(t *testing.T) {
	t.Parallel()
	store := &memTOTPStore{}
	disabled, err := service.NewTotpService(store, service.MasterKeyConfig{}, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	_, err = disabled.BeginEnrollment(context.Background(), beginP("o", "u", "a"))
	if !errors.Is(err, service.ErrTOTPDisabled) {
		t.Fatalf("disabled: %v", err)
	}
}

func TestUnit_TotpService_NotReadyAndNilRepo(t *testing.T) {
	t.Parallel()
	store := &memTOTPStore{}
	notReady, err := service.NewTotpService(store, service.MasterKeyConfig{}, true, nil)
	if err != nil {
		t.Fatal(err)
	}
	_, err = notReady.BeginEnrollment(context.Background(), beginP("o", "u", "a"))
	if !errors.Is(err, service.ErrTOTPNotReady) {
		t.Fatalf("not ready: %v", err)
	}
	if _, err := service.NewTotpService(nil, service.MasterKeyConfig{}, true, nil); err == nil {
		t.Fatal("expected nil repo error")
	}
}

func TestUnit_TotpService_MissingJWTAndGates(t *testing.T) {
	t.Parallel()
	store := &memTOTPStore{}
	enc, _ := mustMasterEncoded(t)
	noJWT, err := service.NewTotpService(store, service.MasterKeyConfig{Encoded: enc}, true, nil)
	if err != nil {
		t.Fatal(err)
	}
	_, _, err = noJWT.CreateStepUp(context.Background(), stepUpP("o", "u", "123456", 1))
	if !errors.Is(err, service.ErrSessionJWTMissing) {
		t.Fatalf("missing jwt: %v", err)
	}
	ready, err := service.NewTotpService(store, service.MasterKeyConfig{Encoded: enc}, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	_, err = ready.BeginEnrollment(context.Background(), beginP("", "u", "a"))
	if !errors.Is(err, service.ErrInvalidArgument) {
		t.Fatalf("empty org: %v", err)
	}
	_, _, err = ready.CreateStepUp(context.Background(), stepUpP("o", "u", "123456", 1))
	if !errors.Is(err, service.ErrTOTPNotEnrolled) {
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
	if _, err := svc.BeginEnrollment(context.Background(), beginP("org", "user", "acct")); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 5; i++ {
		err := svc.ConfirmEnrollment(context.Background(), confirmP("org", "user", "000000"))
		if !errors.Is(err, service.ErrTOTPInvalidCode) {
			t.Fatalf("attempt %d: %v", i, err)
		}
	}
	err = svc.ConfirmEnrollment(context.Background(), confirmP("org", "user", "000000"))
	if !errors.Is(err, service.ErrTOTPLockedOut) {
		t.Fatalf("want lockout, got %v", err)
	}
}

func TestUnit_TotpService_ConfirmPendingAndRepoErrors(t *testing.T) {
	t.Parallel()
	enc, mk := mustMasterEncoded(t)
	store := &memTOTPStore{master: mk}
	svc, err := service.NewTotpService(store, service.MasterKeyConfig{Encoded: enc, KeyID: ""}, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := svc.BeginEnrollment(context.Background(), beginP("org", "user", "acct")); err != nil {
		t.Fatal(err)
	}
	err = svc.ConfirmEnrollment(context.Background(), confirmP("org", "user", "000000"))
	if !errors.Is(err, service.ErrTOTPInvalidCode) {
		t.Fatalf("bad code: %v", err)
	}
	secret := store.plaintext(t, "org", "user")
	code, err := totp.GenerateCode(secret, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	_, _, err = svc.CreateStepUp(context.Background(), stepUpP("org", "user", code, 1))
	if !errors.Is(err, service.ErrTOTPNotEnrolled) {
		t.Fatalf("pending stepup: %v", err)
	}
	if err := svc.ConfirmEnrollment(context.Background(), confirmP("org", "user", code)); err != nil {
		t.Fatal(err)
	}
	err = svc.ConfirmEnrollment(context.Background(), confirmP("org", "user", code))
	if !errors.Is(err, service.ErrTOTPAlreadyDone) {
		t.Fatalf("already done confirm: %v", err)
	}
}

type errGetStore struct {
	memTOTPStore
	getErr error
}

func (e *errGetStore) Get(ctx context.Context, orgID, userID string) (repository.TotpSecretRow, error) {
	if e.getErr != nil {
		return repository.TotpSecretRow{}, e.getErr
	}
	return e.memTOTPStore.Get(ctx, orgID, userID)
}

func TestUnit_TotpService_RepoGetErrorSurfaces(t *testing.T) {
	t.Parallel()
	enc, mk := mustMasterEncoded(t)
	store := &errGetStore{memTOTPStore: memTOTPStore{master: mk}, getErr: errors.New("db down")}
	svc, err := service.NewTotpService(store, service.MasterKeyConfig{Encoded: enc}, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	_, err = svc.BeginEnrollment(context.Background(), beginP("o", "u", "a"))
	if err == nil || err.Error() != "db down" {
		t.Fatalf("want db down, got %v", err)
	}
}

func TestUnit_TotpService_ReleaseOnNotEnrolledAndRepoErrors(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	gate, err := service.NewRedisTOTPAttempts(rdb, 3, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	enc, mk := mustMasterEncoded(t)
	store := &memTOTPStore{master: mk}
	svc, err := service.NewTotpService(store, service.MasterKeyConfig{Encoded: enc, KeyID: "v1"}, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	svc.WithAttemptGate(gate)

	_, _, err = svc.CreateStepUp(context.Background(), stepUpP("org", "user", "123456", 1))
	if !errors.Is(err, service.ErrTOTPNotEnrolled) {
		t.Fatalf("not enrolled: %v", err)
	}
	// Three Allows after Release must still succeed (reservation undone).
	for i := 0; i < 3; i++ {
		_, _, err = svc.CreateStepUp(context.Background(), stepUpP("org", "user", "123456", 1))
		if !errors.Is(err, service.ErrTOTPNotEnrolled) {
			t.Fatalf("iter %d: %v", i, err)
		}
	}

	errStore := &errGetStore{memTOTPStore: memTOTPStore{master: mk}, getErr: errors.New("db down")}
	svc2, err := service.NewTotpService(errStore, service.MasterKeyConfig{Encoded: enc}, true, mustIssuer(t))
	if err != nil {
		t.Fatal(err)
	}
	svc2.WithAttemptGate(gate)
	err = svc2.ConfirmEnrollment(context.Background(), confirmP("org2", "user2", "000000"))
	if err == nil || err.Error() != "db down" {
		t.Fatalf("confirm repo err: %v", err)
	}
	if err := gate.Allow("org2", "user2"); err != nil {
		t.Fatalf("reservation should have been released: %v", err)
	}
}
