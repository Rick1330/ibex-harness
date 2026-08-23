package embedder

import (
	"fmt"
	"sort"
	"strings"
)

// Registry maps deployment Profile keys to Embedder implementations (read-only after New).
type Registry struct {
	byProfile map[Profile]Embedder
}

// NewRegistry constructs a registry from profile → impl.
func NewRegistry(byProfile map[Profile]Embedder) (*Registry, error) {
	out := make(map[Profile]Embedder, len(byProfile))
	for profile, emb := range byProfile {
		if err := registerOne(out, profile, emb); err != nil {
			return nil, err
		}
	}
	return &Registry{byProfile: out}, nil
}

func registerOne(dst map[Profile]Embedder, profile Profile, emb Embedder) error {
	key := Profile(strings.TrimSpace(string(profile)))
	if key == "" || !ValidProfile(key) {
		return fmt.Errorf("%w: %q", ErrUnknownProfile, profile)
	}
	if emb == nil {
		return fmt.Errorf("%w: nil embedder for %q", ErrMissingEmbedder, key)
	}
	if got := emb.Profile(); got != key {
		return fmt.Errorf("%w: key %q embedder reports %q", ErrUnknownProfile, key, got)
	}
	if _, dup := dst[key]; dup {
		return fmt.Errorf("%w: %q", ErrDuplicateProfile, key)
	}
	dst[key] = emb
	return nil
}

// ForProfile returns the embedder for profile or ErrUnknownProfile.
func (r *Registry) ForProfile(profile Profile) (Embedder, error) {
	if r == nil {
		return nil, ErrUnknownProfile
	}
	key := Profile(strings.TrimSpace(string(profile)))
	emb, ok := r.byProfile[key]
	if !ok {
		return nil, fmt.Errorf("%w: %q", ErrUnknownProfile, key)
	}
	return emb, nil
}

// Profiles returns sorted profile keys present in the registry.
func (r *Registry) Profiles() []Profile {
	if r == nil {
		return nil
	}
	out := make([]Profile, 0, len(r.byProfile))
	for p := range r.byProfile {
		out = append(out, p)
	}
	sort.Slice(out, func(i, j int) bool { return out[i] < out[j] })
	return out
}
