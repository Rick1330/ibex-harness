package embedder

import "errors"

var (
	// ErrUnknownProfile is returned for unrecognized or empty profile keys.
	ErrUnknownProfile = errors.New("unknown embedding profile")
	// ErrDuplicateProfile is returned when two embedders claim the same profile.
	ErrDuplicateProfile = errors.New("duplicate embedding profile")
	// ErrMissingEmbedder is returned when a required profile has no implementation.
	ErrMissingEmbedder = errors.New("missing embedder implementation")
	// ErrGeometryMismatch is returned when Dimensions/ModelID do not match expected config.
	ErrGeometryMismatch = errors.New("embedding geometry mismatch")
	// ErrEmptyBatch is returned when Embed is called with no texts.
	ErrEmptyBatch = errors.New("empty embedding batch")
	// ErrBatchTooLarge is returned when the batch exceeds MaxBatchTexts.
	ErrBatchTooLarge = errors.New("embedding batch too large")
	// ErrTextTooLong is returned when a text exceeds MaxTextBytes.
	ErrTextTooLong = errors.New("embedding text too long")
	// ErrInvalidVector is returned when a backend yields wrong-length or non-finite vectors.
	ErrInvalidVector = errors.New("invalid embedding vector")
)
