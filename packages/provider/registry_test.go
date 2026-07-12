package provider

import (
	"context"
	"errors"
	"sync"
	"testing"
)

type stubProvider struct {
	name   string
	models []string
}

func (s stubProvider) Complete(_ context.Context, _ Request) (Response, error) {
	return Response{}, nil
}

func (s stubProvider) Name() string { return s.name }

func (s stubProvider) SupportedModels() []string { return s.models }

func TestUnit_Registry_ForKnownModel(t *testing.T) {
	t.Parallel()
	openai := stubProvider{name: "openai", models: []string{"gpt-4o", "gpt-4o-mini"}}
	reg, err := NewRegistry(openai)
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}

	got, err := reg.For("gpt-4o")
	if err != nil {
		t.Fatalf("For: %v", err)
	}
	if got.Name() != "openai" {
		t.Fatalf("provider name = %q, want openai", got.Name())
	}
}

func TestUnit_Registry_ForUnknownModel(t *testing.T) {
	t.Parallel()
	reg, err := NewRegistry(stubProvider{name: "openai", models: []string{"gpt-4o"}})
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}

	_, err = reg.For("claude-3-5-sonnet-20241022")
	if err != ErrNoProviderForModel {
		t.Fatalf("err = %v, want ErrNoProviderForModel", err)
	}
}

func TestUnit_Registry_EmptyRegistry(t *testing.T) {
	t.Parallel()
	reg, err := NewRegistry()
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}

	_, err = reg.For("gpt-4o")
	if err != ErrNoProviderForModel {
		t.Fatalf("err = %v, want ErrNoProviderForModel", err)
	}
}

func TestUnit_Registry_DuplicateModelReturnsError(t *testing.T) {
	t.Parallel()
	a := stubProvider{name: "openai", models: []string{"gpt-4o"}}
	b := stubProvider{name: "azure", models: []string{"gpt-4o"}}

	_, err := NewRegistry(a, b)
	if !errors.Is(err, ErrDuplicateModel) {
		t.Fatalf("err = %v, want ErrDuplicateModel", err)
	}
}

func TestUnit_Registry_ConcurrentFor(t *testing.T) {
	t.Parallel()
	reg, err := NewRegistry(stubProvider{name: "openai", models: []string{"gpt-4o"}})
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}

	var wg sync.WaitGroup
	for range 32 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			p, err := reg.For("gpt-4o")
			if err != nil {
				t.Errorf("For: %v", err)
				return
			}
			if p.Name() != "openai" {
				t.Errorf("name = %q", p.Name())
			}
		}()
	}
	wg.Wait()
}

func TestUnit_Registry_NilFor(t *testing.T) {
	t.Parallel()
	var reg *Registry

	_, err := reg.For("gpt-4o")
	if err != ErrNoProviderForModel {
		t.Fatalf("err = %v, want ErrNoProviderForModel", err)
	}
}
