package grpcserver

import (
	"context"
	"testing"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

// Finding S04: one service secret admitted validate, revoke, consume-step-up
// and issue, and none of the four calls named an org. These tests pin the two
// halves of the fix: the credential split, and the org assertion on the three
// org-scoped methods.
const (
	testLifecycleToken = "lifecycle-secret"
	testIssueToken     = "issue-secret"
	testOrgID          = "org-a"
	testOtherOrgID     = "org-b"
)

var orgScopedMethods = []string{
	"/ibex.auth.v1.AuthService/ValidateOperatorSession",
	"/ibex.auth.v1.AuthService/RevokeOperatorSession",
	"/ibex.auth.v1.AuthService/ConsumeStepUp",
}

func splitServiceTokens() ServiceTokens {
	return ServiceTokens{Lifecycle: testLifecycleToken, Issue: testIssueToken}
}

func metadataContext(pairs ...string) context.Context {
	return metadata.NewIncomingContext(context.Background(), metadata.Pairs(pairs...))
}

// assertedOrgContext builds the context the interceptor produces for a
// service-authenticated call that named orgID.
func assertedOrgContext(t *testing.T, orgID string) context.Context {
	t.Helper()
	ctx, err := withExpectedOrg(metadataContext(expectedOrgMetadataKey, orgID))
	if err != nil {
		t.Fatalf("expected org context: %v", err)
	}
	return ctx
}

// runInterceptor reports whether the handler ran, and the interceptor error.
func runInterceptor(ic grpc.UnaryServerInterceptor, ctx context.Context, method string) (bool, error) {
	called := false
	_, err := ic(ctx, &authv1.ValidateOperatorSessionRequest{}, &grpc.UnaryServerInfo{FullMethod: method},
		func(context.Context, any) (any, error) {
			called = true
			return &authv1.ValidateOperatorSessionResponse{}, nil
		})
	return called, err
}

// noPATSvalidator fails the test if the PAT path is taken.
func noPATValidator(t *testing.T) *stubTokenValidator {
	t.Helper()
	return &stubTokenValidator{fn: func(context.Context, string) (*authv1.ValidateTokenResponse, error) {
		t.Fatal("PAT validator must not run for a service-token call")
		return nil, nil
	}}
}

func TestServiceTokenSplit_IssueTokenIsRefusedOnOrgScopedMethods(t *testing.T) {
	t.Parallel()

	ic := AuthzUnaryInterceptorWithServiceTokens(noPATValidator(t), splitServiceTokens())
	ctx := metadataContext(serviceTokenMetadataKey, testIssueToken, expectedOrgMetadataKey, testOrgID)
	for _, method := range orgScopedMethods {
		t.Run(method, func(t *testing.T) {
			t.Parallel()
			called, err := runInterceptor(ic, ctx, method)
			if status.Code(err) != codes.Unauthenticated {
				t.Fatalf("code: got %v want Unauthenticated", status.Code(err))
			}
			if called {
				t.Fatal("issue credential must not reach an org-scoped handler")
			}
		})
	}
}

func TestServiceTokenSplit_LifecycleTokenIsRefusedOnIssue(t *testing.T) {
	t.Parallel()

	ic := AuthzUnaryInterceptorWithServiceTokens(noPATValidator(t), splitServiceTokens())
	ctx := metadataContext(serviceTokenMetadataKey, testLifecycleToken, expectedOrgMetadataKey, testOrgID)
	called, err := runInterceptor(ic, ctx, issueOperatorSessionMethod)
	if status.Code(err) != codes.Unauthenticated {
		t.Fatalf("code: got %v want Unauthenticated", status.Code(err))
	}
	if called {
		t.Fatal("lifecycle credential must not reach IssueOperatorSession")
	}
}

func TestServiceTokenSplit_IssueTokenReachesIssue(t *testing.T) {
	t.Parallel()

	ic := AuthzUnaryInterceptorWithServiceTokens(noPATValidator(t), splitServiceTokens())
	called, err := runInterceptor(ic, metadataContext(serviceTokenMetadataKey, testIssueToken), issueOperatorSessionMethod)
	if err != nil || !called {
		t.Fatalf("issue credential on issue: err=%v called=%v", err, called)
	}
}

func TestServiceTokenSplit_OrgScopedCallRequiresOrgAssertion(t *testing.T) {
	t.Parallel()

	ic := AuthzUnaryInterceptorWithServiceTokens(noPATValidator(t), splitServiceTokens())
	cases := []struct {
		name  string
		pairs []string
	}{
		{name: "absent", pairs: []string{serviceTokenMetadataKey, testLifecycleToken}},
		{name: "empty", pairs: []string{serviceTokenMetadataKey, testLifecycleToken, expectedOrgMetadataKey, " "}},
		{
			name: "duplicated",
			pairs: []string{
				serviceTokenMetadataKey, testLifecycleToken,
				expectedOrgMetadataKey, testOrgID,
				expectedOrgMetadataKey, testOtherOrgID,
			},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			ctx := metadataContext(tc.pairs...)
			for _, method := range orgScopedMethods {
				called, err := runInterceptor(ic, ctx, method)
				if status.Code(err) != codes.PermissionDenied {
					t.Fatalf("%s: code: got %v want PermissionDenied", method, status.Code(err))
				}
				if called {
					t.Fatalf("%s: handler ran without an org assertion", method)
				}
			}
		})
	}
}

func TestServiceTokenSplit_AssertedOrgIsAttached(t *testing.T) {
	t.Parallel()

	ic := AuthzUnaryInterceptorWithServiceTokens(noPATValidator(t), splitServiceTokens())
	ctx := metadataContext(serviceTokenMetadataKey, testLifecycleToken, expectedOrgMetadataKey, testOrgID)
	var asserted string
	var ok bool
	_, err := ic(ctx, &authv1.ValidateOperatorSessionRequest{},
		&grpc.UnaryServerInfo{FullMethod: orgScopedMethods[0]},
		func(handlerCtx context.Context, _ any) (any, error) {
			asserted, ok = ExpectedOrgFromContext(handlerCtx)
			return &authv1.ValidateOperatorSessionResponse{}, nil
		})
	if err != nil {
		t.Fatalf("interceptor error: %v", err)
	}
	if !ok {
		t.Fatal("handler saw no asserted org")
	}
	if asserted != testOrgID {
		t.Fatalf("asserted org: got %q want %q", asserted, testOrgID)
	}
}

func TestServiceTokenSplit_MismatchedAssertionIsRefusedByHandlers(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		call func(*Server, context.Context) error
	}{
		{
			name: "validate",
			call: func(s *Server, ctx context.Context) error {
				_, err := s.ValidateOperatorSession(ctx, &authv1.ValidateOperatorSessionRequest{AccessToken: "access"})
				return err
			},
		},
		{
			name: "revoke",
			call: func(s *Server, ctx context.Context) error {
				_, err := s.RevokeOperatorSession(ctx, &authv1.RevokeOperatorSessionRequest{
					AccessToken: "access-proof", SessionId: "sid", FamilyId: "fam",
				})
				return err
			},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			sess := &fakeSessionIssuer{
				accessProof:   sessionjwt.Claims{Subject: "u", OrgID: testOrgID, SessionID: "sid", FamilyID: "fam", JTI: "jti"},
				refreshProof:  sessionjwt.Claims{Subject: "u", OrgID: testOrgID, SessionID: "sid", FamilyID: "fam", JTI: "jti"},
				consumeClaims: sessionjwt.Claims{Subject: "u", OrgID: testOrgID, SessionID: "sid", Action: "a"},
			}
			srv := totpServer(t, nil, sess)
			err := tc.call(srv, assertedOrgContext(t, testOtherOrgID))
			if status.Code(err) != codes.PermissionDenied {
				t.Fatalf("code: got %v want PermissionDenied", status.Code(err))
			}
			if sess.revokeCalls != 0 {
				t.Fatalf("revoke ran for another org: calls=%d", sess.revokeCalls)
			}
			if sess.consumeCalls != 0 {
				t.Fatalf("consume ran for another org: calls=%d", sess.consumeCalls)
			}
		})
	}
}

func TestServiceTokenSplit_ConsumeBindsProofToAssertedOrg(t *testing.T) {
	t.Parallel()

	sess := &fakeSessionIssuer{
		consumeClaims: sessionjwt.Claims{Subject: "u", OrgID: testOrgID, SessionID: "sid", Action: "a"},
	}
	_, err := totpServer(t, nil, sess).ConsumeStepUp(
		assertedOrgContext(t, testOtherOrgID), &authv1.ConsumeStepUpRequest{
			StepUpToken: "tok", ExpectedSubject: "u", ExpectedSessionId: "sid", ExpectedAction: "a",
		})
	if status.Code(err) != codes.Unauthenticated {
		t.Fatalf("code: got %v want Unauthenticated", status.Code(err))
	}
	if sess.consumeExpect.OrgID != testOtherOrgID {
		t.Fatalf("proof verified against %q, want the asserted org", sess.consumeExpect.OrgID)
	}
	if sess.consumeCalls != 0 {
		t.Fatalf("another org's proof was consumed: calls=%d", sess.consumeCalls)
	}
}

func TestServiceTokenSplit_MatchingAssertionKeepsBehaviour(t *testing.T) {
	t.Parallel()

	t.Run("validate", func(t *testing.T) {
		t.Parallel()
		sess := &fakeSessionIssuer{
			accessProof: sessionjwt.Claims{Subject: "u", OrgID: testOrgID, SessionID: "sid", JTI: "jti", Permissions: 3},
		}
		resp, err := totpServer(t, nil, sess).ValidateOperatorSession(
			assertedOrgContext(t, testOrgID), &authv1.ValidateOperatorSessionRequest{AccessToken: "access"})
		if err != nil || resp.GetOrgId() != testOrgID {
			t.Fatalf("validate: resp=%v err=%v", resp, err)
		}
	})

	t.Run("revoke", func(t *testing.T) {
		t.Parallel()
		sess := &fakeSessionIssuer{
			accessProof: sessionjwt.Claims{Subject: "u", OrgID: testOrgID, SessionID: "sid", FamilyID: "fam", JTI: "jti"},
		}
		if _, err := totpServer(t, nil, sess).RevokeOperatorSession(
			assertedOrgContext(t, testOrgID), &authv1.RevokeOperatorSessionRequest{
				AccessToken: "access-proof", SessionId: "sid", FamilyId: "fam",
			}); err != nil {
			t.Fatalf("revoke: %v", err)
		}
		if sess.revokeCalls != 1 {
			t.Fatalf("revoke calls: got %d want 1", sess.revokeCalls)
		}
	})

	t.Run("consume", func(t *testing.T) {
		t.Parallel()
		sess := &fakeSessionIssuer{
			consumeClaims: sessionjwt.Claims{Subject: "u", OrgID: testOrgID, SessionID: "sid", Action: "a"},
		}
		if _, err := totpServer(t, nil, sess).ConsumeStepUp(
			assertedOrgContext(t, testOrgID), &authv1.ConsumeStepUpRequest{
				StepUpToken: "tok", ExpectedSubject: "u", ExpectedSessionId: "sid", ExpectedAction: "a",
			}); err != nil {
			t.Fatalf("consume: %v", err)
		}
		if sess.consumeCalls != 1 || sess.consumeExpect.OrgID != testOrgID {
			t.Fatalf("consume: calls=%d expect=%+v", sess.consumeCalls, sess.consumeExpect)
		}
	})
}

func TestServiceTokenSplit_ConsumeRefusesContradictingAssertions(t *testing.T) {
	t.Parallel()

	sess := &fakeSessionIssuer{
		consumeClaims: sessionjwt.Claims{Subject: "u", OrgID: testOrgID, SessionID: "sid", Action: "a"},
	}
	_, err := totpServer(t, nil, sess).ConsumeStepUp(
		assertedOrgContext(t, testOrgID), &authv1.ConsumeStepUpRequest{
			StepUpToken: "tok", ExpectedSubject: "u", ExpectedOrgId: testOtherOrgID,
			ExpectedSessionId: "sid", ExpectedAction: "a",
		})
	if status.Code(err) != codes.PermissionDenied {
		t.Fatalf("code: got %v want PermissionDenied", status.Code(err))
	}
	if sess.consumeCalls != 0 {
		t.Fatalf("contradicting request consumed a proof: calls=%d", sess.consumeCalls)
	}
}

func TestServiceTokenSplit_PATPathIsUnaffected(t *testing.T) {
	t.Parallel()

	ic := AuthzUnaryInterceptorWithServiceTokens(&stubTokenValidator{fn: func(_ context.Context, bearer string) (*authv1.ValidateTokenResponse, error) {
		if bearer != "pat" {
			t.Fatalf("bearer: %q", bearer)
		}
		return &authv1.ValidateTokenResponse{OrgId: testOrgID}, nil
	}}, splitServiceTokens())
	called, err := runInterceptor(ic, metadataContext("authorization", "Bearer pat"), orgScopedMethods[0])
	if err != nil || !called {
		t.Fatalf("PAT call: err=%v called=%v", err, called)
	}
}
