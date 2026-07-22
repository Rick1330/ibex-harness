package provider

import (
	"context"
	"testing"
)

type ctxStubProvider struct{ name string }

func (s ctxStubProvider) Complete(context.Context, Request) (Response, error) {
	return Response{}, nil
}
func (s ctxStubProvider) Name() string              { return s.name }
func (s ctxStubProvider) SupportedModels() []string { return []string{"gpt-4o"} }

func TestUnit_ProviderContext_RoundTrip(t *testing.T) {
	t.Parallel()
	stub := ctxStubProvider{name: "openai"}
	ctx := WithProvider(context.Background(), stub)
	got, ok := ProviderFromContext(ctx)
	if !ok {
		t.Fatal("expected provider")
	}
	if got.Name() != "openai" {
		t.Fatalf("name=%q", got.Name())
	}
}

func TestUnit_ProviderFromContext_Missing(t *testing.T) {
	t.Parallel()
	_, ok := ProviderFromContext(context.Background())
	if ok {
		t.Fatal("expected missing")
	}
}
