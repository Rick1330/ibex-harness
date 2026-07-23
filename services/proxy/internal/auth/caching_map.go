package auth

import (
	"errors"

	"github.com/Rick1330/ibex-harness/packages/authcache"
)

func mapToAuthcacheErr(err error) error {
	if errors.Is(err, ErrInvalidToken) {
		return authcache.ErrInvalidToken
	}
	if errors.Is(err, ErrAuthUnavailable) {
		return authcache.ErrUnavailable
	}
	return err
}

func mapFromAuthcacheErr(err error) error {
	if errors.Is(err, authcache.ErrInvalidToken) {
		return ErrInvalidToken
	}
	if errors.Is(err, authcache.ErrUnavailable) {
		return ErrAuthUnavailable
	}
	return err
}

func proxyResultToAuthcache(res *ValidateResult) *authcache.Result {
	return &authcache.Result{
		OrgID:       res.OrgID,
		Permissions: res.Permissions,
		AgentID:     res.AgentID,
		UserID:      res.UserID,
		TokenID:     res.TokenID,
		ExpiresAt:   res.ExpiresAt,
	}
}

func authcacheResultToProxy(res *authcache.Result) *ValidateResult {
	return &ValidateResult{
		OrgID:       res.OrgID,
		Permissions: res.Permissions,
		AgentID:     res.AgentID,
		UserID:      res.UserID,
		TokenID:     res.TokenID,
		ExpiresAt:   res.ExpiresAt,
		FromCache:   res.FromCache,
	}
}
