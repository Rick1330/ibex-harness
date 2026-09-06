package responsepipeline

import (
	"context"
	"fmt"
)

type ibexMetadataCtxKey struct{}

// IbexMetadata is the top-level `ibex` JSON block embedded in non-streaming
// chat completion responses when IBEX_CONTEXT_EMBED_METADATA is enabled
// (API_DOCUMENTATION.md / milestone 3.5.D.3). Field names are part of the
// public contract — keep them stable.
type IbexMetadata struct {
	TraceID           string `json:"trace_id"`
	SessionID         string `json:"session_id"`
	MemoriesInjected  int32  `json:"memories_injected"`
	ContextTokensUsed int32  `json:"context_tokens_used"`
	ContextAssemblyMs int64  `json:"context_assembly_ms"`
	ProxyOverheadMs   int64  `json:"proxy_overhead_ms"`
}

// WithIbexMetadata stores request-scoped assembly metadata for IBEXMetadataStage.
// Callers attach this only when Assemble was attempted; absence is a legitimate
// no-op (flag on but Skip-Memory / disabled / nil client for this request).
func WithIbexMetadata(ctx context.Context, meta IbexMetadata) context.Context {
	return context.WithValue(ctx, ibexMetadataCtxKey{}, meta)
}

// IbexMetadataFromContext returns metadata previously stored with WithIbexMetadata.
func IbexMetadataFromContext(ctx context.Context) (IbexMetadata, bool) {
	meta, ok := ctx.Value(ibexMetadataCtxKey{}).(IbexMetadata)
	return meta, ok
}

// IBEXMetadataStage embeds the `ibex` block into non-streaming responses.
// It is not SecurityCritical: missing or malformed metadata fails open
// (skip embed) rather than failing the client response — Track C degradation
// correctness stays headers-first; body embed is opt-in observability.
type IBEXMetadataStage struct{}

func (IBEXMetadataStage) Name() string { return "ibex_metadata" }

// Process injects the `ibex` top-level key when metadata is present on ctx.
// No-op (dirty untouched) when metadata is absent — does not force re-encode.
func (IBEXMetadataStage) Process(ctx context.Context, resp *ChatResponse) (*ChatResponse, error) {
	meta, ok := IbexMetadataFromContext(ctx)
	if !ok {
		return resp, nil
	}
	if err := resp.SetExtra("ibex", meta); err != nil {
		// Fail-open: pipeline logs + restores snapshot; client still gets upstream body.
		return nil, fmt.Errorf("embed ibex metadata: %w", err)
	}
	return resp, nil
}
