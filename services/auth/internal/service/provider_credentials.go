package service

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"

	ibexcrypto "github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
)

var (
	// ErrProviderCredentialNotFound is returned when no BYO credential exists.
	ErrProviderCredentialNotFound = repository.ErrProviderCredentialNotFound
	// ErrCredentialsMasterKeyMissing is returned when the KEK is not configured.
	ErrCredentialsMasterKeyMissing = errors.New("credentials master key not configured")
	// ErrInvalidProviderName is returned for unsupported provider_name values.
	ErrInvalidProviderName = errors.New("invalid provider name")
	// ErrEmptyAPIKey is returned when plaintext api_key is empty.
	ErrEmptyAPIKey = errors.New("api key required")
)

var allowedProviders = map[string]struct{}{
	"openai":           {},
	"anthropic":        {},
	"azure_openai":     {},
	"bedrock":          {},
	"vllm_self_hosted": {},
}

// ProviderCredentialMetadata is the non-secret view of a stored credential.
type ProviderCredentialMetadata struct {
	ProviderName    string
	Status          string
	KeyHint         string
	BaseURL         string
	EncryptionKeyID string
	LastValidatedAt *time.Time
}

// GetProviderCredentialResult is the decrypt result for proxy resolution.
type GetProviderCredentialResult struct {
	APIKey            string
	BaseURL           string
	IsPlatformDefault bool
}

// providerCredentialStore is the persistence port for sealed credentials.
type providerCredentialStore interface {
	Upsert(ctx context.Context, row repository.ProviderCredentialRow) (repository.ProviderCredentialRow, error)
	FindByOrgProvider(ctx context.Context, orgID, providerName string) (repository.ProviderCredentialRow, error)
	ListByOrg(ctx context.Context, orgID string) ([]repository.ProviderCredentialRow, error)
	Delete(ctx context.Context, orgID, providerName string) error
}

// ProviderCredentialService seals and loads org provider credentials.
type ProviderCredentialService struct {
	repo   providerCredentialStore
	master ibexcrypto.MasterKey
	keyID  string
	ready  bool
}

// NewProviderCredentialService constructs a credential service.
// When masterKeyEncoded is empty, ready is false and mutating/decrypt ops fail closed.
func NewProviderCredentialService(repo providerCredentialStore, masterKeyEncoded, keyID string) (*ProviderCredentialService, error) {
	if repo == nil {
		return nil, fmt.Errorf("provider credential service: nil repo")
	}
	if keyID == "" {
		keyID = "v1"
	}
	svc := &ProviderCredentialService{repo: repo, keyID: keyID}
	if strings.TrimSpace(masterKeyEncoded) == "" {
		return svc, nil
	}
	mk, err := ibexcrypto.ParseMasterKeyBase64(masterKeyEncoded)
	if err != nil {
		return nil, fmt.Errorf("provider credential service: %w", err)
	}
	svc.master = mk
	svc.ready = true
	return svc, nil
}

// CreateInput is the upsert request after Management API validation.
type CreateInput struct {
	OrgID        string
	ProviderName string
	APIKey       string
	BaseURL      string
}

// OrgProviderRef identifies one org-scoped provider credential row.
type OrgProviderRef struct {
	OrgID        string
	ProviderName string
}

// Create seals and upserts a provider credential.
func (s *ProviderCredentialService) Create(ctx context.Context, in CreateInput) (ProviderCredentialMetadata, error) {
	if !s.ready {
		return ProviderCredentialMetadata{}, ErrCredentialsMasterKeyMissing
	}
	provider, err := normalizeProviderName(in.ProviderName)
	if err != nil {
		return ProviderCredentialMetadata{}, err
	}
	apiKey := strings.TrimSpace(in.APIKey)
	if apiKey == "" {
		return ProviderCredentialMetadata{}, ErrEmptyAPIKey
	}
	sealed, err := ibexcrypto.Seal(s.master, s.keyID, []byte(apiKey))
	if err != nil {
		return ProviderCredentialMetadata{}, err
	}
	row, err := s.repo.Upsert(ctx, repository.ProviderCredentialRow{
		OrgID:           strings.TrimSpace(in.OrgID),
		ProviderName:    provider,
		Ciphertext:      sealed.Ciphertext,
		WrappedDEK:      sealed.WrappedDEK,
		EncryptionKeyID: sealed.KeyID,
		KeyHint:         keyHint(apiKey),
		BaseURL:         sql.NullString{String: strings.TrimSpace(in.BaseURL), Valid: strings.TrimSpace(in.BaseURL) != ""},
		Status:          "active",
	})
	if err != nil {
		return ProviderCredentialMetadata{}, err
	}
	return metadataFromRow(row), nil
}

// Get decrypts a credential or reports platform-default when no row exists.
func (s *ProviderCredentialService) Get(ctx context.Context, ref OrgProviderRef) (GetProviderCredentialResult, error) {
	provider, err := normalizeProviderName(ref.ProviderName)
	if err != nil {
		return GetProviderCredentialResult{}, err
	}
	row, err := s.repo.FindByOrgProvider(ctx, strings.TrimSpace(ref.OrgID), provider)
	if errors.Is(err, repository.ErrProviderCredentialNotFound) {
		return GetProviderCredentialResult{IsPlatformDefault: true}, nil
	}
	if err != nil {
		return GetProviderCredentialResult{}, err
	}
	if !s.ready {
		return GetProviderCredentialResult{}, ErrCredentialsMasterKeyMissing
	}
	plain, err := ibexcrypto.Open(s.master, ibexcrypto.SealedBlob{
		Ciphertext: row.Ciphertext,
		WrappedDEK: row.WrappedDEK,
		KeyID:      row.EncryptionKeyID,
	})
	if err != nil {
		return GetProviderCredentialResult{}, err
	}
	baseURL := ""
	if row.BaseURL.Valid {
		baseURL = row.BaseURL.String
	}
	return GetProviderCredentialResult{
		APIKey:  string(plain),
		BaseURL: baseURL,
	}, nil
}

// List returns non-secret metadata for an org.
func (s *ProviderCredentialService) List(ctx context.Context, orgID string) ([]ProviderCredentialMetadata, error) {
	rows, err := s.repo.ListByOrg(ctx, strings.TrimSpace(orgID))
	if err != nil {
		return nil, err
	}
	out := make([]ProviderCredentialMetadata, 0, len(rows))
	for _, row := range rows {
		out = append(out, metadataFromRow(row))
	}
	return out, nil
}

// Delete removes a credential row.
func (s *ProviderCredentialService) Delete(ctx context.Context, ref OrgProviderRef) error {
	provider, err := normalizeProviderName(ref.ProviderName)
	if err != nil {
		return err
	}
	return s.repo.Delete(ctx, strings.TrimSpace(ref.OrgID), provider)
}

func normalizeProviderName(raw string) (string, error) {
	name := strings.TrimSpace(strings.ToLower(raw))
	if _, ok := allowedProviders[name]; !ok {
		return "", ErrInvalidProviderName
	}
	return name, nil
}

func keyHint(apiKey string) string {
	if len(apiKey) < 5 {
		return "[REDACTED]"
	}
	return apiKey[len(apiKey)-4:]
}

func metadataFromRow(row repository.ProviderCredentialRow) ProviderCredentialMetadata {
	meta := ProviderCredentialMetadata{
		ProviderName:    row.ProviderName,
		Status:          row.Status,
		KeyHint:         row.KeyHint,
		EncryptionKeyID: row.EncryptionKeyID,
	}
	if row.BaseURL.Valid {
		meta.BaseURL = row.BaseURL.String
	}
	if row.LastValidatedAt.Valid {
		t := row.LastValidatedAt.Time
		meta.LastValidatedAt = &t
	}
	return meta
}
