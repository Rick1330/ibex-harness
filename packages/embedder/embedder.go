package embedder

import "context"

// Embedder produces embedding vectors for text batches.
// Implementations must be safe for concurrent use after construction.
// All vectors from a single Embed call use the same model geometry.
type Embedder interface {
	// Embed returns one L2-normalized float32 vector per input text.
	// Length of the result slice equals len(texts); each vector length equals Dimensions().
	Embed(ctx context.Context, texts []string) ([][]float32, error)

	// Name returns the backend identifier (e.g. "stub", "tei", "openai", "local").
	Name() string

	// ModelID returns the model identifier (e.g. "all-MiniLM-L6-v2", "BAAI/bge-m3").
	ModelID() string

	// Dimensions returns the embedding vector length for this backend.
	Dimensions() int

	// Profile returns the deployment profile this backend serves.
	Profile() Profile
}
