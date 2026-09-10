package service_test

import (
	"context"
	"database/sql"
	"encoding/base64"
	"errors"
	"testing"
	"time"

	ibexcrypto "github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
)

type memCredStore struct {
	rows map[string]repository.ProviderCredentialRow
	err  error
}

func (m *memCredStore) key(orgID, provider string) string {
	return orgID + "\x00" + provider
}

func (m *memCredStore) Upsert(_ context.Context, row repository.ProviderCredentialRow) (repository.ProviderCredentialRow, error) {
	if m.err != nil {
		return repository.ProviderCredentialRow{}, m.err
	}
	if m.rows == nil {
		m.rows = map[string]repository.ProviderCredentialRow{}
	}
	row.ID = "id-1"
	row.CreatedAt = time.Now().UTC()
	row.UpdatedAt = row.CreatedAt
	m.rows[m.key(row.OrgID, row.ProviderName)] = row
	return row, nil
}

func (m *memCredStore) FindByOrgProvider(_ context.Context, orgID, providerName string) (repository.ProviderCredentialRow, error) {
	if m.err != nil {
		return repository.ProviderCredentialRow{}, m.err
	}
	row, ok := m.rows[m.key(orgID, providerName)]
	if !ok {
		return repository.ProviderCredentialRow{}, repository.ErrProviderCredentialNotFound
	}
	return row, nil
}

func (m *memCredStore) ListByOrg(_ context.Context, orgID string) ([]repository.ProviderCredentialRow, error) {
	if m.err != nil {
		return nil, m.err
	}
	out := make([]repository.ProviderCredentialRow, 0)
	prefix := orgID + "\x00"
	for k, row := range m.rows {
		if len(k) >= len(prefix) && k[:len(prefix)] == prefix {
			out = append(out, row)
		}
	}
	return out, nil
}

func (m *memCredStore) Delete(_ context.Context, orgID, providerName string) error {
	if m.err != nil {
		return m.err
	}
	key := m.key(orgID, providerName)
	if _, ok := m.rows[key]; !ok {
		return repository.ErrProviderCredentialNotFound
	}
	delete(m.rows, key)
	return nil
}

func testMasterEncoded(t *testing.T) string {
	t.Helper()
	raw := ibexcrypto.GenerateRandomBytes(ibexcrypto.MasterKeySize)
	return base64.StdEncoding.EncodeToString(raw)
}

func TestUnit_ProviderCredentialService_RoundTrip(t *testing.T) {
	t.Parallel()
	store := &memCredStore{}
	svc := mustCredService(t, store)
	meta, err := svc.Create(context.Background(), service.CreateInput{
		OrgID: "org-1", ProviderName: "openai", APIKey: "sk-test-abcdef", BaseURL: "https://example.com",
	})
	if err != nil {
		t.Fatal(err)
	}
	assertMetaHint(t, meta, "cdef")
	assertGetKey(t, svc, "org-1", "openai", "sk-test-abcdef", "https://example.com")
	assertListCount(t, svc, "org-1", 1)
	if err := svc.Delete(context.Background(), service.OrgProviderRef{OrgID: "org-1", ProviderName: "openai"}); err != nil {
		t.Fatal(err)
	}
	got, err := svc.Get(context.Background(), service.OrgProviderRef{OrgID: "org-1", ProviderName: "openai"})
	if err != nil || !got.IsPlatformDefault {
		t.Fatalf("expected platform default after delete: %+v err=%v", got, err)
	}
}

func mustCredService(t *testing.T, store *memCredStore) *service.ProviderCredentialService {
	t.Helper()
	svc, err := service.NewProviderCredentialService(store, service.MasterKeyConfig{
		Encoded: testMasterEncoded(t), KeyID: "v1",
	})
	if err != nil {
		t.Fatal(err)
	}
	return svc
}

func assertMetaHint(t *testing.T, meta service.ProviderCredentialMetadata, hint string) {
	t.Helper()
	if meta.KeyHint != hint || meta.ProviderName != "openai" {
		t.Fatalf("meta=%+v", meta)
	}
}

func assertGetKey(t *testing.T, svc *service.ProviderCredentialService, org, provider, key, base string) {
	t.Helper()
	got, err := svc.Get(context.Background(), service.OrgProviderRef{OrgID: org, ProviderName: provider})
	if err != nil || got.IsPlatformDefault || got.APIKey != key || got.BaseURL != base {
		t.Fatalf("got=%+v err=%v", got, err)
	}
}

func assertListCount(t *testing.T, svc *service.ProviderCredentialService, org string, n int) {
	t.Helper()
	listed, err := svc.List(context.Background(), org)
	if err != nil || len(listed) != n {
		t.Fatalf("list=%+v err=%v", listed, err)
	}
}

func TestUnit_ProviderCredentialService_NotReady(t *testing.T) {
	t.Parallel()
	svc, err := service.NewProviderCredentialService(&memCredStore{}, service.MasterKeyConfig{})
	if err != nil {
		t.Fatal(err)
	}
	_, err = svc.Create(context.Background(), service.CreateInput{
		OrgID: "o", ProviderName: "openai", APIKey: "sk-long-enough",
	})
	if !errors.Is(err, service.ErrCredentialsMasterKeyMissing) {
		t.Fatalf("err=%v", err)
	}
}

func TestUnit_ProviderCredentialService_Validation(t *testing.T) {
	t.Parallel()
	svc, err := service.NewProviderCredentialService(&memCredStore{}, service.MasterKeyConfig{
		Encoded: testMasterEncoded(t),
	})
	if err != nil {
		t.Fatal(err)
	}
	_, err = svc.Create(context.Background(), service.CreateInput{
		OrgID: "o", ProviderName: "nope", APIKey: "sk-long-enough",
	})
	if !errors.Is(err, service.ErrInvalidProviderName) {
		t.Fatalf("err=%v", err)
	}
	_, err = svc.Create(context.Background(), service.CreateInput{
		OrgID: "o", ProviderName: "openai", APIKey: "   ",
	})
	if !errors.Is(err, service.ErrEmptyAPIKey) {
		t.Fatalf("err=%v", err)
	}
}

func TestUnit_ProviderCredentialService_ShortKeyHint(t *testing.T) {
	t.Parallel()
	svc, err := service.NewProviderCredentialService(&memCredStore{}, service.MasterKeyConfig{
		Encoded: testMasterEncoded(t),
	})
	if err != nil {
		t.Fatal(err)
	}
	meta, err := svc.Create(context.Background(), service.CreateInput{
		OrgID: "o", ProviderName: "openai", APIKey: "abcd",
	})
	if err != nil {
		t.Fatal(err)
	}
	if meta.KeyHint != "[REDACTED]" {
		t.Fatalf("hint=%q", meta.KeyHint)
	}
}

func TestUnit_ProviderCredentialService_GetWithoutReadyFailsClosed(t *testing.T) {
	t.Parallel()
	shared := &memCredStore{}
	mk := testMasterEncoded(t)
	ready, err := service.NewProviderCredentialService(shared, service.MasterKeyConfig{Encoded: mk})
	if err != nil {
		t.Fatal(err)
	}
	_, err = ready.Create(context.Background(), service.CreateInput{
		OrgID: "o", ProviderName: "openai", APIKey: "sk-seeded-key",
	})
	if err != nil {
		t.Fatal(err)
	}
	notReady, err := service.NewProviderCredentialService(shared, service.MasterKeyConfig{})
	if err != nil {
		t.Fatal(err)
	}
	_, err = notReady.Get(context.Background(), service.OrgProviderRef{OrgID: "o", ProviderName: "openai"})
	if !errors.Is(err, service.ErrCredentialsMasterKeyMissing) {
		t.Fatalf("err=%v", err)
	}
}

func TestUnit_ProviderCredentialService_NilRepo(t *testing.T) {
	t.Parallel()
	_, err := service.NewProviderCredentialService(nil, service.MasterKeyConfig{})
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_ProviderCredentialService_StoreAndDecryptErrors(t *testing.T) {
	t.Parallel()
	store := &memCredStore{err: errors.New("db down")}
	svc := mustCredService(t, store)
	_, err := svc.Create(context.Background(), service.CreateInput{
		OrgID: "o", ProviderName: "openai", APIKey: "sk-long-enough",
	})
	if err == nil {
		t.Fatal("expected upsert error")
	}
	_, err = svc.List(context.Background(), "o")
	if err == nil {
		t.Fatal("expected list error")
	}
	if err := svc.Delete(context.Background(), service.OrgProviderRef{OrgID: "o", ProviderName: "openai"}); err == nil {
		t.Fatal("expected delete error")
	}
	if err := svc.Delete(context.Background(), service.OrgProviderRef{OrgID: "o", ProviderName: "nope"}); !errors.Is(err, service.ErrInvalidProviderName) {
		t.Fatalf("err=%v", err)
	}

	ok := &memCredStore{}
	ready := mustCredService(t, ok)
	_, err = ready.Create(context.Background(), service.CreateInput{
		OrgID: "o", ProviderName: "openai", APIKey: "sk-seed",
	})
	if err != nil {
		t.Fatal(err)
	}
	row := ok.rows[ok.key("o", "openai")]
	row.Ciphertext[len(row.Ciphertext)-1] ^= 0xff
	ok.rows[ok.key("o", "openai")] = row
	_, err = ready.Get(context.Background(), service.OrgProviderRef{OrgID: "o", ProviderName: "openai"})
	if err == nil {
		t.Fatal("expected open failure")
	}
}

func TestUnit_ProviderCredentialService_MetadataValidatedAt(t *testing.T) {
	t.Parallel()
	store := &memCredStore{}
	svc := mustCredService(t, store)
	_, err := svc.Create(context.Background(), service.CreateInput{
		OrgID: "o", ProviderName: "anthropic", APIKey: "sk-ant-xxxx",
	})
	if err != nil {
		t.Fatal(err)
	}
	row := store.rows[store.key("o", "anthropic")]
	now := time.Now().UTC().Truncate(time.Second)
	row.LastValidatedAt = sql.NullTime{Time: now, Valid: true}
	row.BaseURL = sql.NullString{String: "https://example.com", Valid: true}
	store.rows[store.key("o", "anthropic")] = row
	listed, err := svc.List(context.Background(), "o")
	if err != nil || len(listed) != 1 {
		t.Fatalf("list=%+v err=%v", listed, err)
	}
	if listed[0].LastValidatedAt == nil || !listed[0].LastValidatedAt.Equal(now) {
		t.Fatalf("meta=%+v", listed[0])
	}
	if listed[0].BaseURL != "https://example.com" {
		t.Fatalf("base=%q", listed[0].BaseURL)
	}
}
