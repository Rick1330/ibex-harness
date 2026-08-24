package embedder

// Input limits for Embed (fail closed before upstream).
const (
	MaxBatchTexts = 64
	MaxTextBytes  = 32 * 1024 // 32 KiB per text
)
