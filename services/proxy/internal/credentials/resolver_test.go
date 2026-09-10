package credentials_test

import (
	"context"
	"errors"
	"testing"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/credentials"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type fakeGetter struct {
	resp  *authv1.GetProviderCredentialResponse
	err   error
	calls int
}

func (f *fakeGetter) GetProviderCredential(
	_ context.Context,
	_ *authv1.GetProviderCredentialRequest,
	_ ...grpc.CallOption,
) (*authv1.GetProviderCredentialResponse, error) {
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	return f.resp, nil
}

func TestUnit_CachedResolver_PlatformDefaultCached(t *testing.T) {
	t.Parallel()
	fake := &fakeGetter{resp: &authv1.GetProviderCredentialResponse{IsPlatformDefault: true}}
	r, err := credentials.NewCachedResolver(fake, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	got, err := r.Resolve(context.Background(), "org", "openai", "tok")
	if err != nil || !got.PlatformDefault {
		t.Fatalf("got=%+v err=%v", got, err)
	}
	_, _ = r.Resolve(context.Background(), "org", "openai", "tok")
	if fake.calls != 1 {
		t.Fatalf("calls=%d want 1", fake.calls)
	}
}

func TestUnit_CachedResolver_BYOCached(t *testing.T) {
	t.Parallel()
	fake := &fakeGetter{resp: &authv1.GetProviderCredentialResponse{ApiKey: "sk-byo", BaseUrl: "https://example.com"}}
	r, err := credentials.NewCachedResolver(fake, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	got, err := r.Resolve(context.Background(), "org", "openai", "tok")
	if err != nil || got.PlatformDefault || got.APIKey != "sk-byo" {
		t.Fatalf("got=%+v err=%v", got, err)
	}
	_, _ = r.Resolve(context.Background(), "org", "openai", "tok")
	if fake.calls != 1 {
		t.Fatalf("calls=%d want 1", fake.calls)
	}
}

func TestUnit_CachedResolver_ErrorsNotCached(t *testing.T) {
	t.Parallel()
	fake := &fakeGetter{err: status.Error(codes.Unavailable, "down")}
	r, err := credentials.NewCachedResolver(fake, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	_, err = r.Resolve(context.Background(), "org", "openai", "tok")
	if err == nil {
		t.Fatal("expected error")
	}
	fake.err = nil
	fake.resp = &authv1.GetProviderCredentialResponse{IsPlatformDefault: true}
	got, err := r.Resolve(context.Background(), "org", "openai", "tok")
	if err != nil || !got.PlatformDefault {
		t.Fatalf("got=%+v err=%v", got, err)
	}
	if fake.calls != 2 {
		t.Fatalf("calls=%d want 2", fake.calls)
	}
}

func TestUnit_CachedResolver_NilClient(t *testing.T) {
	t.Parallel()
	_, err := credentials.NewCachedResolver(nil, 0)
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_CachedResolver_WrapsRPCError(t *testing.T) {
	t.Parallel()
	fake := &fakeGetter{err: errors.New("boom")}
	r, err := credentials.NewCachedResolver(fake, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	_, err = r.Resolve(context.Background(), "o", "openai", "t")
	if err == nil {
		t.Fatal("expected error")
	}
}
