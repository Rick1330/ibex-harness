package modelpolicy

import (
	"context"
	"fmt"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/google/uuid"
)

// OrgAwareRegistry gates Registry.For with per-org model policies (ADR-0075).
type OrgAwareRegistry struct {
	base    *provider.Registry
	cache   *Cache
	metrics Metrics
}

// NewOrgAwareRegistry wraps base with policy evaluation via cache.
func NewOrgAwareRegistry(base *provider.Registry, cache *Cache, m Metrics) (*OrgAwareRegistry, error) {
	if base == nil {
		return nil, fmt.Errorf("modelpolicy: base registry is required")
	}
	if cache == nil {
		return nil, fmt.Errorf("modelpolicy: cache is required")
	}
	if m == nil {
		m = NoopMetrics{}
	}
	return &OrgAwareRegistry{base: base, cache: cache, metrics: m}, nil
}

// ForOrg evaluates org policy then delegates to Registry.For.
func (r *OrgAwareRegistry) ForOrg(ctx context.Context, orgID uuid.UUID, model string) (provider.Provider, error) {
	if orgID == uuid.Nil {
		return nil, fmt.Errorf("%w: missing org_id", ErrPolicyUnavailable)
	}
	policies, err := r.cache.PoliciesForOrg(ctx, orgID)
	if err != nil {
		return nil, err
	}
	dec, err := EvaluatePolicies(policies, model)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrPolicyUnavailable, err)
	}
	if dec.Matched && !dec.Allowed {
		r.metrics.IncDeny()
		return nil, ErrModelNotAllowedForOrg
	}
	return r.base.For(model)
}

// Base returns the underlying platform registry.
func (r *OrgAwareRegistry) Base() *provider.Registry { return r.base }

// PassthroughRegistry adapts *provider.Registry to ForOrg without policies.
type PassthroughRegistry struct {
	Base *provider.Registry
}

// ForOrg ignores orgID and calls Registry.For.
func (p PassthroughRegistry) ForOrg(_ context.Context, _ uuid.UUID, model string) (provider.Provider, error) {
	if p.Base == nil {
		return nil, provider.ErrNoProviderForModel
	}
	return p.Base.For(model)
}

// ResolveCandidateModel applies precedence: request model, else agent default_model.
func ResolveCandidateModel(requestModel string, defaults AgentDefaults) string {
	if m := strings.TrimSpace(requestModel); m != "" {
		return m
	}
	return strings.TrimSpace(defaults.DefaultModel)
}
