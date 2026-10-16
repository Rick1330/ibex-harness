// Package providercap contains the immutable, provenance-aware provider capability manifest used for pre-dispatch validation.
package providercap

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const CurrentVersion = "provider-capability-manifest.v1"

var (
	ErrInvalidManifest       = errors.New("invalid provider capability manifest")
	ErrStaleManifest         = errors.New("stale provider capability manifest")
	ErrCapabilityUnknown     = errors.New("provider capability unknown")
	ErrCapabilityUnsupported = errors.New("provider capability unsupported")
)

type State string

const (
	StateSupported   State = "supported"
	StateUnsupported State = "unsupported"
	StateUnverified  State = "unverified"
)

type Provenance struct {
	SourceURL  string    `json:"source_url"`
	Title      string    `json:"title"`
	AccessedAt time.Time `json:"accessed_at"`
}
type Claim struct {
	State      State       `json:"state"`
	Provenance *Provenance `json:"provenance,omitempty"`
}
type Model struct {
	Provider        string           `json:"provider"`
	Model           string           `json:"model"`
	ContextWindow   int              `json:"context_window"`
	MaxOutputTokens int              `json:"max_output_tokens"`
	TokenizerFamily string           `json:"tokenizer_family"`
	Endpoint        string           `json:"endpoint"`
	Capabilities    map[string]Claim `json:"capabilities"`
}
type Manifest struct {
	Version     string    `json:"version"`
	GeneratedAt time.Time `json:"generated_at"`
	ExpiresAt   time.Time `json:"expires_at"`
	Models      []Model   `json:"models"`
}
type Snapshot struct {
	manifest Manifest
	models   map[string]Model
}

func Load(r io.Reader, now time.Time) (*Snapshot, error) {
	return load(r, now, false)
}

// LoadAllowStale loads structurally valid evidence even after expiry; Require rejects stale snapshots.
func LoadAllowStale(r io.Reader, now time.Time) (*Snapshot, error) {
	return load(r, now, true)
}

func load(r io.Reader, now time.Time, allowStale bool) (*Snapshot, error) {
	if now.IsZero() {
		now = time.Now().UTC()
	}
	dec := json.NewDecoder(r)
	dec.DisallowUnknownFields()
	var m Manifest
	if err := dec.Decode(&m); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidManifest, err)
	}
	var extra any
	if err := dec.Decode(&extra); err != io.EOF {
		return nil, fmt.Errorf("%w: trailing JSON", ErrInvalidManifest)
	}
	if err := validate(m, now, allowStale); err != nil {
		return nil, err
	}
	models := make(map[string]Model, len(m.Models))
	for _, model := range m.Models {
		model.Capabilities = cloneClaims(model.Capabilities)
		models[model.Provider+"\x00"+model.Model] = model
	}
	return &Snapshot{manifest: m, models: models}, nil
}
func LoadBytes(b []byte, now time.Time) (*Snapshot, error) { return Load(bytes.NewReader(b), now) }
func LoadFile(path string, now time.Time) (*Snapshot, error) {
	return loadFile(path, now, false)
}

// LoadFileAllowStale is the startup-safe file loader.
func LoadFileAllowStale(path string, now time.Time) (*Snapshot, error) {
	return loadFile(path, now, true)
}

func loadFile(path string, now time.Time, allowStale bool) (*Snapshot, error) {
	// path is operator-supplied configuration (IBEX_PROVIDER_CAPABILITY_MANIFEST)
	// or a fixed repo-relative seed path, never end-user request input.
	f, err := os.Open(filepath.Clean(path)) // nosemgrep: go.lang.security.audit.file-access -- operator-configured manifest path, not user input
	if err != nil {
		return nil, err
	}
	defer func() { _ = f.Close() }()
	return load(f, now, allowStale)
}
func LoadDefault(now time.Time) (*Snapshot, error) {
	return loadDefault(now, false)
}

// LoadDefaultAllowStale is intended for startup; runtime Require still denies stale claims.
func LoadDefaultAllowStale(now time.Time) (*Snapshot, error) {
	return loadDefault(now, true)
}

func loadDefault(now time.Time, allowStale bool) (*Snapshot, error) {
	if p := strings.TrimSpace(os.Getenv("IBEX_PROVIDER_CAPABILITY_MANIFEST")); p != "" {
		return loadConfiguredManifest(p, now, allowStale)
	}
	return loadSeedManifest(now, allowStale)
}

func loadConfiguredManifest(path string, now time.Time, allowStale bool) (*Snapshot, error) {
	return loadFileByMode(path, now, allowStale)
}

func loadFileByMode(path string, now time.Time, allowStale bool) (*Snapshot, error) {
	if allowStale {
		return LoadFileAllowStale(path, now)
	}
	return LoadFile(path, now)
}

func loadSeedManifest(now time.Time, allowStale bool) (*Snapshot, error) {
	var last error
	for _, p := range seedManifestPaths() {
		s, err := loadFileByMode(p, now, allowStale)
		if err == nil {
			return s, nil
		}
		last = err
	}
	return nil, fmt.Errorf("provider capability manifest: %w", last)
}

func seedManifestPaths() []string {
	const rel = "infra/provider-capabilities/manifest.v1.json"
	paths := []string{rel}
	wd, err := os.Getwd()
	if err != nil {
		return paths
	}
	for dir := wd; dir != filepath.Dir(dir); dir = filepath.Dir(dir) {
		paths = append(paths, filepath.Join(dir, rel))
	}
	return paths
}

func validate(m Manifest, now time.Time, allowStale bool) error {
	if err := validateVersion(m); err != nil {
		return err
	}
	if err := validateFreshness(m, now, allowStale); err != nil {
		return err
	}
	return validateModels(m.Models, now)
}

func validateVersion(m Manifest) error {
	if m.Version != CurrentVersion {
		return fmt.Errorf("%w: version %q", ErrInvalidManifest, m.Version)
	}
	return nil
}

func validateFreshness(m Manifest, now time.Time, allowStale bool) error {
	if err := validateFreshnessWindow(m); err != nil {
		return err
	}
	if now.Before(m.GeneratedAt) {
		return fmt.Errorf("%w: generated_at is in the future", ErrInvalidManifest)
	}
	if allowStale {
		return nil
	}
	if now.Before(m.ExpiresAt) {
		return nil
	}
	return fmt.Errorf("%w: expired at %s", ErrStaleManifest, m.ExpiresAt.UTC().Format(time.RFC3339))
}

func validateFreshnessWindow(m Manifest) error {
	if m.GeneratedAt.IsZero() {
		return invalidFreshnessWindow()
	}
	if m.ExpiresAt.IsZero() {
		return invalidFreshnessWindow()
	}
	if !m.ExpiresAt.After(m.GeneratedAt) {
		return invalidFreshnessWindow()
	}
	return nil
}

func invalidFreshnessWindow() error {
	return fmt.Errorf("%w: invalid freshness window", ErrInvalidManifest)
}

func validateModels(models []Model, now time.Time) error {
	if len(models) == 0 {
		return fmt.Errorf("%w: models is required", ErrInvalidManifest)
	}
	seen := make(map[string]struct{}, len(models))
	for _, model := range models {
		if err := validateModel(model, seen, now); err != nil {
			return err
		}
	}
	return nil
}

func validateModel(model Model, seen map[string]struct{}, now time.Time) error {
	if err := validateModelIdentity(model); err != nil {
		return err
	}
	key := model.Provider + "\x00" + model.Model
	if _, ok := seen[key]; ok {
		return fmt.Errorf("%w: duplicate model %s/%s", ErrInvalidManifest, model.Provider, model.Model)
	}
	seen[key] = struct{}{}
	if err := validateModelLimits(model); err != nil {
		return err
	}
	if err := validateModelCompleteness(model); err != nil {
		return err
	}
	return validateClaims(model, now)
}

func validateModelIdentity(model Model) error {
	if strings.TrimSpace(model.Provider) == "" {
		return modelIdentityRequired()
	}
	if strings.TrimSpace(model.Model) == "" {
		return modelIdentityRequired()
	}
	if strings.TrimSpace(model.Endpoint) == "" {
		return modelIdentityRequired()
	}
	return nil
}

func modelIdentityRequired() error {
	return fmt.Errorf("%w: model identity is required", ErrInvalidManifest)
}

func validateModelCompleteness(model Model) error {
	if model.TokenizerFamily == "" {
		return incompleteModel(model.Model)
	}
	if len(model.Capabilities) == 0 {
		return incompleteModel(model.Model)
	}
	return nil
}

func incompleteModel(name string) error {
	return fmt.Errorf("%w: incomplete model %s", ErrInvalidManifest, name)
}

func validateModelLimits(model Model) error {
	if model.ContextWindow <= 0 {
		return invalidLimits(model.Model)
	}
	if model.MaxOutputTokens <= 0 {
		return invalidLimits(model.Model)
	}
	if model.MaxOutputTokens > model.ContextWindow {
		return invalidLimits(model.Model)
	}
	return nil
}

func invalidLimits(name string) error {
	return fmt.Errorf("%w: invalid limits for %s", ErrInvalidManifest, name)
}

func validateClaims(model Model, now time.Time) error {
	for name, claim := range model.Capabilities {
		if err := validateClaim(model.Model, name, claim, now); err != nil {
			return err
		}
	}
	return nil
}

func validateClaim(modelName, claimName string, claim Claim, now time.Time) error {
	if !validClaimState(claim.State) {
		return fmt.Errorf("%w: invalid state for %s/%s", ErrInvalidManifest, modelName, claimName)
	}
	if err := validateClaimProvenance(modelName, claimName, claim); err != nil {
		return err
	}
	if claim.Provenance != nil && claim.Provenance.AccessedAt.After(now) {
		return fmt.Errorf("%w: future provenance for %s/%s", ErrInvalidManifest, modelName, claimName)
	}
	return nil
}

func validClaimState(state State) bool {
	switch state {
	case StateSupported, StateUnsupported, StateUnverified:
		return true
	default:
		return false
	}
}

func validateClaimProvenance(modelName, claimName string, claim Claim) error {
	if claim.State != StateSupported {
		return nil
	}
	if claim.Provenance == nil {
		return claimLacksProvenance(modelName, claimName)
	}
	if strings.TrimSpace(claim.Provenance.SourceURL) == "" {
		return claimLacksProvenance(modelName, claimName)
	}
	if claim.Provenance.AccessedAt.IsZero() {
		return claimLacksProvenance(modelName, claimName)
	}
	return nil
}

func claimLacksProvenance(modelName, claimName string) error {
	return fmt.Errorf("%w: supported claim %s/%s lacks provenance", ErrInvalidManifest, modelName, claimName)
}
func cloneClaims(in map[string]Claim) map[string]Claim {
	out := make(map[string]Claim, len(in))
	for k, v := range in {
		out[k] = cloneClaim(v)
	}
	return out
}
func cloneClaim(in Claim) Claim {
	out := in
	if in.Provenance != nil {
		p := *in.Provenance
		out.Provenance = &p
	}
	return out
}
func cloneModel(in Model) Model {
	out := in
	out.Capabilities = cloneClaims(in.Capabilities)
	return out
}
func cloneManifest(in Manifest) Manifest {
	out := in
	out.Models = make([]Model, len(in.Models))
	for i, m := range in.Models {
		out.Models[i] = cloneModel(m)
	}
	return out
}
func (s *Snapshot) Manifest() Manifest { return cloneManifest(s.manifest) }
func (s *Snapshot) Lookup(provider, model string) (Model, bool) {
	if s == nil {
		return Model{}, false
	}
	m, ok := s.models[provider+"\x00"+model]
	return cloneModel(m), ok
}
func (s *Snapshot) Require(provider, model string, names ...string) error {
	if s == nil {
		return fmt.Errorf("%w: nil snapshot", ErrCapabilityUnknown)
	}
	if !time.Now().UTC().Before(s.manifest.ExpiresAt) {
		return fmt.Errorf("%w: manifest expired at %s", ErrCapabilityUnknown, s.manifest.ExpiresAt.UTC().Format(time.RFC3339))
	}
	m, ok := s.Lookup(provider, model)
	if !ok {
		return fmt.Errorf("%w: %s/%s", ErrCapabilityUnknown, provider, model)
	}
	for _, name := range names {
		claim, ok := m.Capabilities[name]
		if !ok || claim.State == StateUnverified {
			return fmt.Errorf("%w: %s for %s/%s", ErrCapabilityUnknown, name, provider, model)
		}
		if claim.State != StateSupported {
			return fmt.Errorf("%w: %s for %s/%s", ErrCapabilityUnsupported, name, provider, model)
		}
	}
	return nil
}
