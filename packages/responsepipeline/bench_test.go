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
