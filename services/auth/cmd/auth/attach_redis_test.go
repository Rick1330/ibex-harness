package main

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/config"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

type nopTotpRepo struct{}

func (nopTotpRepo) UpsertPending(context.Context, repository.TotpSecretRow) error { return nil }

func (nopTotpRepo) Get(context.Context, string, string) (repository.TotpSecretRow, error) {
	return repository.TotpSecretRow{}, repository.ErrTotpSecretNotFound
}

func (nopTotpRepo) ConfirmCiphertext(context.Context, repository.ConfirmCiphertextParams) error {
	return nil
}

func mustTestIssuer(t *testing.T) *sessionjwt.Issuer {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	pemBytes := pem.EncodeToMemory(&pem.Block{
		Type:  "RSA PRIVATE KEY",
		Bytes: x509.MarshalPKCS1PrivateKey(priv),
	})
	iss, err := sessionjwt.NewIssuer(sessionjwt.IssuerConfig{
		PrivateKeyPEM: sessionjwt.PrivateKeyPEM(string(pemBytes)),
		Issuer:        sessionjwt.TokenIssuer("ibex-test"),
		Audience:      sessionjwt.TokenAudience("ibex-test"),
		AccessTTL:     time.Minute,
		RefreshTTL:    time.Hour,
		StepUpTTL:     time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	return iss
}

func mustNopTotpService(t *testing.T) *service.TotpService {
	t.Helper()
	svc, err := service.NewTotpService(nopTotpRepo{}, service.MasterKeyConfig{}, true, nil)
	if err != nil {
		t.Fatal(err)
	}
	return svc
}

func TestUnit_AttachRedisJTIStore_RequiresRedisWhenIssuerPresent(t *testing.T) {
	t.Parallel()
	err := attachRedisJTIStore(mustTestIssuer(t), nil)
	if err == nil {
		t.Fatal("expected error when JWT issuer is present and redis is nil")
	}
	if !strings.Contains(err.Error(), "REDIS_URL is required when JWT_PRIVATE_KEY_PEM enables session issuance") {
		t.Fatalf("err=%v", err)
	}
}

func TestUnit_AttachRedisJTIStore_NilIssuerAllowsNilRedis(t *testing.T) {
	t.Parallel()
	if err := attachRedisJTIStore(nil, nil); err != nil {
		t.Fatalf("nil issuer must allow nil redis (no session issuance): %v", err)
	}
}

func TestUnit_AttachRedisJTIStore_AttachesWhenRedisPresent(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	if err := attachRedisJTIStore(mustTestIssuer(t), rdb); err != nil {
		t.Fatalf("attach with redis: %v", err)
	}
}

func TestUnit_AttachRedisTOTPAttempts_RequiresRedisWhenEnabled(t *testing.T) {
	t.Parallel()
	cfg := config.Config{TOTPEnabled: true}
	err := attachRedisTOTPAttempts(cfg, mustNopTotpService(t), nil)
	if err == nil {
		t.Fatal("expected error when TOTP enabled and redis is nil")
	}
	if !strings.Contains(err.Error(), "REDIS_URL is required when IBEX_AUTH_TOTP_ENABLED=true") {
		t.Fatalf("err=%v", err)
	}
}

func TestUnit_AttachRedisTOTPAttempts_DisabledAllowsNilRedis(t *testing.T) {
	t.Parallel()
	cfg := config.Config{TOTPEnabled: false}
	if err := attachRedisTOTPAttempts(cfg, mustNopTotpService(t), nil); err != nil {
		t.Fatalf("TOTP disabled must allow nil redis: %v", err)
	}
}

func TestUnit_AttachRedisTOTPAttempts_NilServiceAllowsNilRedis(t *testing.T) {
	t.Parallel()
	cfg := config.Config{TOTPEnabled: true}
	if err := attachRedisTOTPAttempts(cfg, nil, nil); err != nil {
		t.Fatalf("nil totp service short-circuits: %v", err)
	}
}

func TestUnit_AttachRedisTOTPAttempts_AttachesWhenRedisPresent(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	cfg := config.Config{TOTPEnabled: true}
	if err := attachRedisTOTPAttempts(cfg, mustNopTotpService(t), rdb); err != nil {
		t.Fatalf("attach with redis: %v", err)
	}
}
