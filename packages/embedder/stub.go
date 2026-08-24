package embedder

import (
	"context"
	"fmt"
	"hash/fnv"
)

// Stub is a deterministic, L2-normalized embedder for tests and local contract checks.
// It is not a production inference backend (Name returns "stub").
type Stub struct {
	profile Profile
	modelID string
	dim     int
}

// NewStub constructs a stub embedder for the given profile geometry.
func NewStub(profile Profile, modelID string, dim int) (*Stub, error) {
	if !ValidProfile(profile) {
		return nil, fmt.Errorf("%w: %q", ErrUnknownProfile, profile)
	}
	if dim < 1 {
		return nil, fmt.Errorf("%w: dimensions %d", ErrGeometryMismatch, dim)
	}
	if modelID == "" {
		return nil, fmt.Errorf("%w: empty model id", ErrGeometryMismatch)
	}
	return &Stub{profile: profile, modelID: modelID, dim: dim}, nil
}

// NewStubForProfile builds a stub using DefaultGeometry for the profile.
func NewStubForProfile(profile Profile) (*Stub, error) {
	geo, err := DefaultGeometry(profile)
	if err != nil {
		return nil, err
	}
	return NewStub(profile, geo.ModelID, geo.Dimensions)
}

func (s *Stub) Name() string     { return "stub" }
func (s *Stub) ModelID() string  { return s.modelID }
func (s *Stub) Dimensions() int  { return s.dim }
func (s *Stub) Profile() Profile { return s.profile }

// Embed returns deterministic L2-normalized vectors derived from text hashes.
func (s *Stub) Embed(ctx context.Context, texts []string) ([][]float32, error) {
	if s == nil {
		return nil, ErrMissingEmbedder
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if err := ValidateEmbedInput(texts); err != nil {
		return nil, err
	}
	out := make([][]float32, len(texts))
	for i, text := range texts {
		vec, err := s.vectorFor(text)
		if err != nil {
			return nil, err
		}
		out[i] = vec
	}
	if err := ValidateOutputVectors(texts, out, s.dim); err != nil {
		return nil, err
	}
	return out, nil
}

func (s *Stub) vectorFor(text string) ([]float32, error) {
	h := fnv.New64a()
	_, _ = h.Write([]byte(text))
	seed := h.Sum64()
	vec := make([]float32, s.dim)
	for i := 0; i < s.dim; i++ {
		// Mix seed with index for a dense, reproducible pattern.
		x := seed ^ (uint64(i+1) * 0x9e3779b97f4a7c15)
		vec[i] = float32(int64(x%2001)-1000) / 1000.0 // [-1, 1]
	}
	if err := L2NormalizeInPlace(vec); err != nil {
		return nil, err
	}
	return vec, nil
}
