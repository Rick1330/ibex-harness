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

func mustMiniRedis(t *testing.T) redis.UniversalClient {
	t.Helper()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	return rdb
}

func assertErrContains(t *testing.T, err error, needle string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected error containing %q", needle)
	}
	if !strings.Contains(err.Error(), needle) {
		t.Fatalf("err=%v want substring %q", err, needle)
	}
}

func TestUnit_AttachRedisJTIStore(t *testing.T) {
	t.Parallel()
	const needRedis = "REDIS_URL is required when JWT_PRIVATE_KEY_PEM enables session issuance"

	t.Run("requires_redis_when_issuer_present", func(t *testing.T) {
		t.Parallel()
		assertErrContains(t, attachRedisJTIStore(mustTestIssuer(t), nil), needRedis)
	})
	t.Run("nil_issuer_allows_nil_redis", func(t *testing.T) {
		t.Parallel()
		if err := attachRedisJTIStore(nil, nil); err != nil {
			t.Fatalf("nil issuer must allow nil redis: %v", err)
		}
	})
	t.Run("attaches_when_redis_present", func(t *testing.T) {
		t.Parallel()
		if err := attachRedisJTIStore(mustTestIssuer(t), mustMiniRedis(t)); err != nil {
			t.Fatalf("attach with redis: %v", err)
		}
	})
}

func TestUnit_AttachRedisTOTPAttempts(t *testing.T) {
	t.Parallel()
	const needRedis = "REDIS_URL is required when IBEX_AUTH_TOTP_ENABLED=true"

	t.Run("requires_redis_when_enabled", func(t *testing.T) {
		t.Parallel()
		err := attachRedisTOTPAttempts(config.Config{TOTPEnabled: true}, mustNopTotpService(t), nil)
		assertErrContains(t, err, needRedis)
	})
	t.Run("disabled_allows_nil_redis", func(t *testing.T) {
		t.Parallel()
		err := attachRedisTOTPAttempts(config.Config{TOTPEnabled: false}, mustNopTotpService(t), nil)
		if err != nil {
			t.Fatalf("TOTP disabled must allow nil redis: %v", err)
		}
	})
	t.Run("nil_service_allows_nil_redis", func(t *testing.T) {
		t.Parallel()
		err := attachRedisTOTPAttempts(config.Config{TOTPEnabled: true}, nil, nil)
		if err != nil {
			t.Fatalf("nil totp service short-circuits: %v", err)
		}
	})
	t.Run("attaches_when_redis_present", func(t *testing.T) {
		t.Parallel()
		err := attachRedisTOTPAttempts(
			config.Config{TOTPEnabled: true}, mustNopTotpService(t), mustMiniRedis(t),
		)
		if err != nil {
			t.Fatalf("attach with redis: %v", err)
		}
	})
}
