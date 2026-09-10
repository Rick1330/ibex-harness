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

func resolveIn() credentials.ResolveInput {
	return credentials.ResolveInput{OrgID: "org", ProviderName: "openai", AccessToken: "tok"}
}

func TestUnit_CachedResolver_PlatformDefaultCached(t *testing.T) {
	t.Parallel()
	fake := &fakeGetter{resp: &authv1.GetProviderCredentialResponse{IsPlatformDefault: true}}
	r, err := credentials.NewCachedResolver(fake, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	got, err := r.Resolve(context.Background(), resolveIn())
	if err != nil || !got.PlatformDefault {
		t.Fatalf("got=%+v err=%v", got, err)
	}
	_, _ = r.Resolve(context.Background(), resolveIn())
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
	got, err := r.Resolve(context.Background(), resolveIn())
	if err != nil {
		t.Fatalf("resolve err=%v", err)
	}
	if got.PlatformDefault {
		t.Fatalf("expected BYO, got platform default")
	}
	if got.APIKey != "sk-byo" {
		t.Fatalf("APIKey=%q", got.APIKey)
	}
	_, _ = r.Resolve(context.Background(), resolveIn())
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
	_, err = r.Resolve(context.Background(), resolveIn())
	if err == nil {
		t.Fatal("expected error")
	}
	fake.err = nil
	fake.resp = &authv1.GetProviderCredentialResponse{IsPlatformDefault: true}
	got, err := r.Resolve(context.Background(), resolveIn())
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
	_, err = r.Resolve(context.Background(), credentials.ResolveInput{
		OrgID: "o", ProviderName: "openai", AccessToken: "t",
	})
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_CachedResolver_TTLExpiryAndDefaults(t *testing.T) {
	t.Parallel()
	fake := &fakeGetter{resp: &authv1.GetProviderCredentialResponse{ApiKey: "sk"}}
	r, err := credentials.NewCachedResolverWithTimeout(fake, 0, 0)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Unix(1000, 0)
	r.SetClockForTest(func() time.Time { return now })
	if _, err := r.Resolve(context.Background(), resolveIn()); err != nil {
		t.Fatal(err)
	}
	now = now.Add(credentials.DefaultCacheTTL + time.Second)
	if _, err := r.Resolve(context.Background(), resolveIn()); err != nil {
		t.Fatal(err)
	}
	if fake.calls != 2 {
		t.Fatalf("calls=%d want 2 after TTL expiry", fake.calls)
	}
}

func TestUnit_CachedResolver_NotFoundMapped(t *testing.T) {
	t.Parallel()
	fake := &fakeGetter{err: status.Error(codes.NotFound, "missing")}
	r, err := credentials.NewCachedResolver(fake, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	_, err = r.Resolve(context.Background(), resolveIn())
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_CachedResolver_EvictsWhenFull(t *testing.T) {
	t.Parallel()
	fake := &fakeGetter{resp: &authv1.GetProviderCredentialResponse{ApiKey: "sk"}}
	r, err := credentials.NewCachedResolver(fake, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	r.SetMaxCacheForTest(2)
	inputs := make([]credentials.ResolveInput, 3)
	for i := 0; i < 3; i++ {
		inputs[i] = credentials.ResolveInput{
			OrgID: "org", ProviderName: "p" + string(rune('a'+i)), AccessToken: "t",
		}
		if _, err := r.Resolve(context.Background(), inputs[i]); err != nil {
			t.Fatal(err)
		}
	}
	if fake.calls != 3 {
		t.Fatalf("calls=%d", fake.calls)
	}
	for _, in := range inputs {
		if _, err := r.Resolve(context.Background(), in); err != nil {
			t.Fatal(err)
		}
	}
	if fake.calls <= 3 {
		t.Fatalf("expected eviction refetch calls>3, got %d", fake.calls)
	}
}
