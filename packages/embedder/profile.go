package embedder

import "fmt"

// Profile is a deployment-time embedding profile key.
// Profiles are not interchangeable at the vector-search level without migration.
type Profile string

const (
	ProfileCPU    Profile = "cpu"
	ProfileGPU    Profile = "gpu"
	ProfileHosted Profile = "hosted"
)

// ProfileDefaults documents the planned default geometry per profile (ADR-0046).
// M1 does not run TEI/OpenAI; stubs may use these dims for contract tests.
type ProfileDefaults struct {
	ModelID    string
	Dimensions int
}

// DefaultGeometry returns the documented default model/dim for a known profile.
func DefaultGeometry(p Profile) (ProfileDefaults, error) {
	switch p {
	case ProfileCPU:
		return ProfileDefaults{ModelID: "all-MiniLM-L6-v2", Dimensions: 384}, nil
	case ProfileGPU:
		return ProfileDefaults{ModelID: "BAAI/bge-m3", Dimensions: 1024}, nil
	case ProfileHosted:
		// Hosted default for OpenAI text-embedding-3-large (G4.M3); Cohere uses 1024.
		return ProfileDefaults{ModelID: "text-embedding-3-large", Dimensions: 3072}, nil
	default:
		return ProfileDefaults{}, fmt.Errorf("%w: %q", ErrUnknownProfile, p)
	}
}

// ValidProfile reports whether p is a known deployment profile.
func ValidProfile(p Profile) bool {
	switch p {
	case ProfileCPU, ProfileGPU, ProfileHosted:
		return true
	default:
		return false
	}
}
