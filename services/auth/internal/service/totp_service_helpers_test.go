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
	"github.com/redis/go-redis/v9"
)

type memTOTPStore struct {
	mu     sync.Mutex
	rows   map[string]repository.TotpSecretRow
	master ibexcrypto.MasterKey
}

func (m *memTOTPStore) key(ref service.TenantRef) string {
	org, user := ref.KeyParts()
	return org + ":" + user
}

func (m *memTOTPStore) UpsertPending(_ context.Context, row repository.TotpSecretRow) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.rows == nil {
		m.rows = map[string]repository.TotpSecretRow{}
	}
	row.ConfirmedAt = sql.NullTime{}
	m.rows[m.key(service.TenantRef{Org: service.OrgID(row.OrgID), User: service.UserID(row.UserID)})] = row
	return nil
}

func (m *memTOTPStore) Get(_ context.Context, orgID, userID string) (repository.TotpSecretRow, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	row, ok := m.rows[m.key(service.TenantRef{Org: service.OrgID(orgID), User: service.UserID(userID)})]
	if !ok {
		return repository.TotpSecretRow{}, repository.ErrTotpSecretNotFound
	}
	return row, nil
}

func (m *memTOTPStore) ConfirmCiphertext(_ context.Context, p repository.ConfirmCiphertextParams) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	key := m.key(service.TenantRef{Org: service.OrgID(p.OrgID), User: service.UserID(p.UserID)})
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

func (m *memTOTPStore) plaintext(t *testing.T, ref service.TenantRef) string {
	t.Helper()
	org, user := ref.KeyParts()
	row, err := m.Get(context.Background(), org, user)
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

func mustMasterEncoded(t *testing.T) (service.MasterKeyConfig, ibexcrypto.MasterKey) {
	t.Helper()
	raw := ibexcrypto.GenerateRandomBytes(ibexcrypto.MasterKeySize)
	enc := base64.StdEncoding.EncodeToString(raw)
	mk, err := ibexcrypto.ParseMasterKeyBase64(enc)
	if err != nil {
		t.Fatal(err)
	}
	return service.MasterKeyConfig{Encoded: enc, KeyID: "v1"}, mk
}

func mustIssuer(t *testing.T) *sessionjwt.Issuer {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	pemBytes := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(priv)})
	iss, err := sessionjwt.NewIssuer(sessionjwt.IssuerConfig{
		PrivateKeyPEM: sessionjwt.PrivateKeyPEM(string(pemBytes)),
		Issuer:        sessionjwt.TokenIssuer("ibex-auth"),
		Audience:      sessionjwt.TokenAudience("ibex-dashboard"),
		AccessTTL:     time.Minute,
		RefreshTTL:    time.Hour,
		StepUpTTL:     time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	return iss
}

func mustRedisGate(t *testing.T, maxFails int) *service.RedisTOTPAttempts {
	t.Helper()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	gate, err := service.NewRedisTOTPAttempts(rdb, maxFails, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	return gate
}

func beginP(ref service.TenantRef, acct string) service.BeginEnrollmentParams {
	return service.BeginEnrollmentParams{OrgID: ref.Org, UserID: ref.User, AccountName: acct}
}

func confirmP(ref service.TenantRef, code string) service.ConfirmEnrollmentParams {
	return service.ConfirmEnrollmentParams{OrgID: ref.Org, UserID: ref.User, Code: code}
}

func stepUpP(ref service.TenantRef, code string, perms int64) service.CreateStepUpParams {
	return service.CreateStepUpParams{OrgID: ref.Org, UserID: ref.User, Code: code, Permissions: perms}
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
