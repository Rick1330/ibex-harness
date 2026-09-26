package sessionjwt_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
)

type errorJTIStore struct {
	sessionjwt.MemoryJTIStore
	sessionErr error
	familyErr  error
	accessErr  error
	consumeErr error
	revokeErr  error
	stepErr    error
}

func (s *errorJTIStore) SessionRevoked(ctx context.Context, sessionID string) (bool, error) {
	if s.sessionErr != nil {
		return false, s.sessionErr
	}
	return s.MemoryJTIStore.SessionRevoked(ctx, sessionID)
}

func (s *errorJTIStore) FamilyRevoked(ctx context.Context, familyID string) (bool, error) {
	if s.familyErr != nil {
		return false, s.familyErr
	}
	return s.MemoryJTIStore.FamilyRevoked(ctx, familyID)
}

func (s *errorJTIStore) AccessRevoked(ctx context.Context, jti string) (bool, error) {
	if s.accessErr != nil {
		return false, s.accessErr
	}
	return s.MemoryJTIStore.AccessRevoked(ctx, jti)
}

func (s *errorJTIStore) ConsumeOnce(ctx context.Context, jti string, ttl time.Duration) (bool, error) {
	if s.consumeErr != nil {
		return false, s.consumeErr
	}
	return s.MemoryJTIStore.ConsumeOnce(ctx, jti, ttl)
}

func (s *errorJTIStore) RevokeSessionAndFamily(ctx context.Context, sessionID, familyID string, ttl time.Duration) error {
	if s.revokeErr != nil {
		return s.revokeErr
	}
	return s.MemoryJTIStore.RevokeSessionAndFamily(ctx, sessionID, familyID, ttl)
}

func (s *errorJTIStore) RevokeAccess(ctx context.Context, jti string, ttl time.Duration) error {
	if s.accessErr != nil {
		return s.accessErr
	}
	return s.MemoryJTIStore.RevokeAccess(ctx, jti, ttl)
}

func (s *errorJTIStore) ConsumeStepUp(ctx context.Context, jti string, ttl time.Duration) (bool, error) {
	if s.stepErr != nil {
		return false, s.stepErr
	}
	return s.MemoryJTIStore.ConsumeStepUp(ctx, jti, ttl)
}

func TestValidateAccess_PropagatesStoreLookupErrors(t *testing.T) {
	storeErr := errors.New("store down")
	cases := []struct {
		name  string
		store *errorJTIStore
	}{
		{"session", &errorJTIStore{sessionErr: storeErr}},
		{"family", &errorJTIStore{familyErr: storeErr}},
		{"access", &errorJTIStore{accessErr: storeErr}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
			issuer.WithJTIStore(tc.store)
			access, _, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{
				Subject: "u", OrgID: "o", Permissions: 1, SessionID: "s", FamilyID: "f",
			})
			requireNoErr(t, err)
			_, err = issuer.ValidateAccess(context.Background(), sessionjwt.RawToken(access))
			if !errors.Is(err, storeErr) {
				t.Fatalf("want store error, got %v", err)
			}
		})
	}
}

func TestRevokeSession_PropagatesStoreErrors(t *testing.T) {
	storeErr := errors.New("revoke failed")
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	issuer.WithJTIStore(&errorJTIStore{revokeErr: storeErr})
	if err := issuer.RevokeSession(context.Background(), "s", "f", "j"); !errors.Is(err, storeErr) {
		t.Fatalf("want revoke error, got %v", err)
	}
	issuer.WithJTIStore(&errorJTIStore{accessErr: storeErr})
	if err := issuer.RevokeSession(context.Background(), "s", "f", "j"); !errors.Is(err, storeErr) {
		t.Fatalf("want access revoke error, got %v", err)
	}
}

func TestConsumeStepUp_PropagatesStoreErrors(t *testing.T) {
	storeErr := errors.New("step store")
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	access, _, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{
		Subject: "u", OrgID: "o", Permissions: 8, SessionID: "sid",
	})
	requireNoErr(t, err)
	claims, err := issuer.ValidateAccess(context.Background(), sessionjwt.RawToken(access))
	requireNoErr(t, err)
	step, _, err := issuer.IssueStepUp(sessionjwt.IssueStepUpParams{
		Subject: "u", OrgID: "o", Permissions: 8, SessionID: claims.SessionID, Action: "a",
	})
	requireNoErr(t, err)
	expect := sessionjwt.StepUpExpectations{
		Subject: "u", OrgID: "o", SessionID: claims.SessionID, Action: "a", RequiredPermission: 8,
	}

	issuer.WithJTIStore(&errorJTIStore{sessionErr: storeErr})
	if _, err := issuer.ConsumeStepUp(context.Background(), sessionjwt.RawToken(step), expect); !errors.Is(err, storeErr) {
		t.Fatalf("session lookup: %v", err)
	}
	issuer.WithJTIStore(&errorJTIStore{stepErr: storeErr})
	if _, err := issuer.ConsumeStepUp(context.Background(), sessionjwt.RawToken(step), expect); !errors.Is(err, storeErr) {
		t.Fatalf("consume: %v", err)
	}
}

func TestRefreshPair_PropagatesStoreLookupAndConsumeErrors(t *testing.T) {
	storeErr := errors.New("refresh store")
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	_, refresh, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{
		Subject: "u", OrgID: "o", Permissions: 1, SessionID: "s", FamilyID: "f",
	})
	requireNoErr(t, err)

	issuer.WithJTIStore(&errorJTIStore{sessionErr: storeErr})
	if _, _, _, _, err := issuer.RefreshPair(context.Background(), sessionjwt.RefreshToken(refresh)); !errors.Is(err, storeErr) {
		t.Fatalf("session: %v", err)
	}
	issuer.WithJTIStore(&errorJTIStore{familyErr: storeErr})
	if _, _, _, _, err := issuer.RefreshPair(context.Background(), sessionjwt.RefreshToken(refresh)); !errors.Is(err, storeErr) {
		t.Fatalf("family: %v", err)
	}
	issuer.WithJTIStore(&errorJTIStore{consumeErr: storeErr})
	if _, _, _, _, err := issuer.RefreshPair(context.Background(), sessionjwt.RefreshToken(refresh)); !errors.Is(err, storeErr) {
		t.Fatalf("consume: %v", err)
	}
}

func TestRefreshPair_ReusePropagatesRevokeStoreError(t *testing.T) {
	storeErr := errors.New("reuse revoke")
	issuer := mustIssuer(t, time.Minute, time.Hour, time.Minute)
	store := &errorJTIStore{}
	issuer.WithJTIStore(store)
	_, refresh, _, _, err := issuer.IssuePair(sessionjwt.IssuePairParams{
		Subject: "u", OrgID: "o", Permissions: 1, SessionID: "s", FamilyID: "f",
	})
	requireNoErr(t, err)
	_, _, _, _, err = issuer.RefreshPair(context.Background(), sessionjwt.RefreshToken(refresh))
	requireNoErr(t, err)
	store.revokeErr = storeErr
	if _, _, _, _, err := issuer.RefreshPair(context.Background(), sessionjwt.RefreshToken(refresh)); !errors.Is(err, storeErr) {
		t.Fatalf("reuse revoke: %v", err)
	}
}
