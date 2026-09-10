// Package credentials resolves org-scoped BYO provider API keys for the proxy.
package credentials

import (
	"context"
	"fmt"
	"sync"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

const (
	DefaultCacheTTL      = 30 * time.Second
	defaultRPCTimeout    = 50 * time.Millisecond
	maxCachedCredentials = 1024
)

// Result is the resolved credential for one (org, provider) pair.
type Result struct {
	PlatformDefault bool
	APIKey          string
	BaseURL         string
}

// Getter is the AuthService GetProviderCredential port.
type Getter interface {
	GetProviderCredential(
		ctx context.Context,
		req *authv1.GetProviderCredentialRequest,
		opts ...grpc.CallOption,
	) (*authv1.GetProviderCredentialResponse, error)
}

// Resolver loads and caches org provider credentials.
type Resolver interface {
	Resolve(ctx context.Context, orgID, providerName, accessToken string) (Result, error)
}

type cacheEntry struct {
	result    Result
	expiresAt time.Time
}

// CachedResolver wraps Auth Get with a 30s in-memory cache.
// Transport/RPC failures are never cached.
type CachedResolver struct {
	client     Getter
	ttl        time.Duration
	rpcTimeout time.Duration
	now        func() time.Time

	mu    sync.Mutex
	cache map[string]cacheEntry
}

// NewCachedResolver constructs a resolver. client must be non-nil.
func NewCachedResolver(client Getter, ttl time.Duration) (*CachedResolver, error) {
	return NewCachedResolverWithTimeout(client, ttl, defaultRPCTimeout)
}

// NewCachedResolverWithTimeout constructs a resolver with an explicit Auth RPC deadline.
func NewCachedResolverWithTimeout(client Getter, ttl, rpcTimeout time.Duration) (*CachedResolver, error) {
	if client == nil {
		return nil, fmt.Errorf("credentials: nil auth client")
	}
	if ttl <= 0 {
		ttl = DefaultCacheTTL
	}
	if rpcTimeout <= 0 {
		rpcTimeout = defaultRPCTimeout
	}
	return &CachedResolver{
		client:     client,
		ttl:        ttl,
		rpcTimeout: rpcTimeout,
		now:        time.Now,
		cache:      make(map[string]cacheEntry),
	}, nil
}

// Resolve returns platform-default or BYO credentials for the org/provider.
func (r *CachedResolver) Resolve(
	ctx context.Context,
	orgID, providerName, accessToken string,
) (Result, error) {
	key := orgID + "\x00" + providerName
	if hit, ok := r.lookup(key); ok {
		return hit, nil
	}
	result, err := r.fetch(ctx, orgID, providerName, accessToken)
	if err != nil {
		return Result{}, err
	}
	r.store(key, result)
	return result, nil
}

func (r *CachedResolver) lookup(key string) (Result, bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.evictExpiredLocked()
	entry, ok := r.cache[key]
	if !ok {
		return Result{}, false
	}
	return entry.result, true
}

func (r *CachedResolver) store(key string, result Result) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.evictExpiredLocked()
	if len(r.cache) >= maxCachedCredentials {
		// Drop an arbitrary entry to keep the map bounded under churn.
		for existing := range r.cache {
			if existing != key {
				delete(r.cache, existing)
				break
			}
		}
	}
	r.cache[key] = cacheEntry{result: result, expiresAt: r.now().Add(r.ttl)}
}

func (r *CachedResolver) evictExpiredLocked() {
	now := r.now()
	for key, entry := range r.cache {
		if !now.Before(entry.expiresAt) {
			delete(r.cache, key)
		}
	}
}

func (r *CachedResolver) fetch(
	ctx context.Context,
	orgID, providerName, accessToken string,
) (Result, error) {
	md := metadata.Pairs("authorization", "Bearer "+accessToken)
	ctx = metadata.NewOutgoingContext(ctx, md)
	rpcCtx, cancel := context.WithTimeout(ctx, r.rpcTimeout)
	defer cancel()
	resp, err := r.client.GetProviderCredential(rpcCtx, &authv1.GetProviderCredentialRequest{
		OrgId:        orgID,
		ProviderName: providerName,
	})
	if err != nil {
		if st, ok := status.FromError(err); ok && st.Code() == codes.NotFound {
			// Auth Get returns platform-default for missing rows; NotFound is unexpected.
			return Result{}, fmt.Errorf("credentials: get: %w", err)
		}
		return Result{}, fmt.Errorf("credentials: get: %w", err)
	}
	if resp.GetIsPlatformDefault() {
		return Result{PlatformDefault: true}, nil
	}
	return Result{
		APIKey:  resp.GetApiKey(),
		BaseURL: resp.GetBaseUrl(),
	}, nil
}
