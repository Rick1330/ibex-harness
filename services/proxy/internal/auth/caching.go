package auth

import (
	"context"
	"errors"
	"fmt"

	"github.com/Rick1330/ibex-harness/packages/authcache"
	"github.com/Rick1330/ibex-harness/packages/logger"
)

// CacheInvalidator removes cached claims (by hash or token UUID).
type CacheInvalidator interface {
	Invalidate(tokenHash string)
	InvalidateByTokenID(tokenID string)
}

type grpcUpstream struct {
	inner TokenValidator
}

func (u *grpcUpstream) Validate(ctx context.Context, accessToken string) (*authcache.Result, error) {
	res, err := u.inner.Validate(ctx, accessToken)
	if err != nil {
		return nil, mapToAuthcacheErr(err)
	}
	return &authcache.Result{
		OrgID:       res.OrgID,
		Permissions: res.Permissions,
		AgentID:     res.AgentID,
		UserID:      res.UserID,
		TokenID:     res.TokenID,
		ExpiresAt:   res.ExpiresAt,
	}, nil
}

func mapToAuthcacheErr(err error) error {
	switch {
	case errors.Is(err, ErrInvalidToken):
		return authcache.ErrInvalidToken
	case errors.Is(err, ErrAuthUnavailable):
		return authcache.ErrUnavailable
	default:
		return err
	}
}

type cachingTokenValidator struct {
	inner *authcache.CachingValidator
}

// WrapWithCache decorates a TokenValidator with bloom + LRU caching.
// The returned validator also implements CacheInvalidator.
func WrapWithCache(
	inner TokenValidator,
	cfg authcache.Config,
	log *logger.Logger,
	m authcache.Metrics,
) (TokenValidator, error) {
	if inner == nil {
		return nil, fmt.Errorf("auth: wrap cache requires inner validator")
	}
	cv, err := authcache.New(&grpcUpstream{inner: inner}, cfg, log, m)
	if err != nil {
		return nil, err
	}
	return &cachingTokenValidator{inner: cv}, nil
}

func (c *cachingTokenValidator) Validate(ctx context.Context, accessToken string) (*ValidateResult, error) {
	res, err := c.inner.Validate(ctx, accessToken)
	if err != nil {
		return nil, mapFromAuthcacheErr(err)
	}
	return &ValidateResult{
		OrgID:       res.OrgID,
		Permissions: res.Permissions,
		AgentID:     res.AgentID,
		UserID:      res.UserID,
		TokenID:     res.TokenID,
		ExpiresAt:   res.ExpiresAt,
		FromCache:   res.FromCache,
	}, nil
}

func (c *cachingTokenValidator) Invalidate(tokenHash string) {
	c.inner.Invalidate(tokenHash)
}

func (c *cachingTokenValidator) InvalidateByTokenID(tokenID string) {
	c.inner.InvalidateByTokenID(tokenID)
}

func mapFromAuthcacheErr(err error) error {
	switch {
	case errors.Is(err, authcache.ErrInvalidToken):
		return ErrInvalidToken
	case errors.Is(err, authcache.ErrUnavailable):
		return ErrAuthUnavailable
	default:
		return err
	}
}
