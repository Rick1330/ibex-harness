package responsepipeline

import (
	"context"
	"testing"
)

func BenchmarkResponsePipelineNoop(b *testing.B) {
	body := []byte(`{"id":"bench","object":"chat.completion","created":1,"model":"gpt-4o","choices":[{"index":0,"message":{"role":"assistant","content":"hello world"},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15},"system_fingerprint":"fp"}`)
	pipe := NewDefaultPipeline()
	ctx := context.Background()
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		resp, err := Decode(body)
		if err != nil {
			b.Fatal(err)
		}
		out, err := pipe.Run(ctx, resp)
		if err != nil {
			b.Fatal(err)
		}
		if _, err := out.Bytes(); err != nil {
			b.Fatal(err)
		}
	}
}

// BenchmarkResponsePipelineIbexMetadataNoop measures the registered-but-idle path:
// IBEXMetadataStage present, no metadata on ctx → dirty untouched (verbatim Bytes).
func BenchmarkResponsePipelineIbexMetadataNoop(b *testing.B) {
	body := benchChatBody()
	pipe := NewPipeline([]Stage{NoopStage{}, IBEXMetadataStage{}})
	ctx := context.Background()
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		resp, err := Decode(body)
		if err != nil {
			b.Fatal(err)
		}
		out, err := pipe.Run(ctx, resp)
		if err != nil {
			b.Fatal(err)
		}
		if _, err := out.Bytes(); err != nil {
			b.Fatal(err)
		}
	}
}

// BenchmarkResponsePipelineIbexMetadataEmbed measures dirty re-encode when embedding.
func BenchmarkResponsePipelineIbexMetadataEmbed(b *testing.B) {
	body := benchChatBody()
	pipe := NewPipeline([]Stage{NoopStage{}, IBEXMetadataStage{}})
	meta := IbexMetadata{
		TraceID: "bench-trace", SessionID: "bench-session",
		MemoriesInjected: 3, ContextTokensUsed: 100,
		ContextAssemblyMs: 12, ProxyOverheadMs: 8,
	}
	ctx := WithIbexMetadata(context.Background(), meta)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		resp, err := Decode(body)
		if err != nil {
			b.Fatal(err)
		}
		out, err := pipe.Run(ctx, resp)
		if err != nil {
			b.Fatal(err)
		}
		wire, err := out.Bytes()
		if err != nil {
			b.Fatal(err)
		}
		if len(wire) < len(body) {
			b.Fatalf("expected larger body after embed, got %d < %d", len(wire), len(body))
		}
	}
}

func benchChatBody() []byte {
	return []byte(`{"id":"bench","object":"chat.completion","created":1,"model":"gpt-4o","choices":[{"index":0,"message":{"role":"assistant","content":"hello world"},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15},"system_fingerprint":"fp"}`)
}
