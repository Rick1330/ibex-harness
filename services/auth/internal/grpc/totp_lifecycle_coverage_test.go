package grpcserver

import (
	"context"
	"errors"
	"testing"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// issueOnlyIssuer implements sessionIssuerPort but not lifecycleIssuerPort.
type issueOnlyIssuer struct {
	access, refresh string
	aExp, rExp      time.Time
}

func (i *issueOnlyIssuer) IssuePair(sessionjwt.IssuePairParams) (string, string, time.Time, time.Time, error) {
	return i.access, i.refresh, i.aExp, i.rExp, nil
}
func (i *issueOnlyIssuer) RefreshPair(context.Context, sessionjwt.RefreshToken) (string, string, time.Time, time.Time, error) {
	return i.access, i.refresh, i.aExp, i.rExp, nil
}

func TestLifecycleHandlers_NilIssuerAndNotReady(t *testing.T) {
	t.Parallel()
	nilSrv := totpServer(t, nil, nil)
	issueOnly := totpServer(t, nil, &issueOnlyIssuer{access: "a", refresh: "r", aExp: time.Now(), rExp: time.Now()})
	cases := []struct {
		name string
		fn   func(*Server) error
		want codes.Code
	}{
		{"validate nil", func(s *Server) error {
			_, err := s.ValidateOperatorSession(context.Background(), &authv1.ValidateOperatorSessionRequest{AccessToken: "x"})
			return err
		}, codes.FailedPrecondition},
		{"revoke nil", func(s *Server) error {
			_, err := s.RevokeOperatorSession(context.Background(), &authv1.RevokeOperatorSessionRequest{AccessToken: "x"})
			return err
		}, codes.FailedPrecondition},
		{"consume nil", func(s *Server) error {
			_, err := s.ConsumeStepUp(context.Background(), &authv1.ConsumeStepUpRequest{StepUpToken: "x"})
			return err
		}, codes.FailedPrecondition},
		{"validate not ready", func(s *Server) error {
			_, err := s.ValidateOperatorSession(context.Background(), &authv1.ValidateOperatorSessionRequest{AccessToken: "x"})
			return err
		}, codes.FailedPrecondition},
		{"revoke not ready", func(s *Server) error {
			_, err := s.RevokeOperatorSession(context.Background(), &authv1.RevokeOperatorSessionRequest{AccessToken: "x"})
			return err
		}, codes.FailedPrecondition},
		{"consume not ready", func(s *Server) error {
			_, err := s.ConsumeStepUp(context.Background(), &authv1.ConsumeStepUpRequest{StepUpToken: "x"})
			return err
		}, codes.FailedPrecondition},
	}
	for i, tc := range cases {
		srv := nilSrv
		if i >= 3 {
			srv = issueOnly
		}
		t.Run(tc.name, func(t *testing.T) {
			err := tc.fn(srv)
			if status.Code(err) != tc.want {
				t.Fatalf("got %v", err)
			}
		})
	}
}

func TestConsumeStepUp_MapsStoreUnavailable(t *testing.T) {
	t.Parallel()
	sess := &fakeSessionIssuer{consumeErr: errors.New("redis down")}
	srv := totpServer(t, nil, sess)
	if _, err := srv.ConsumeStepUp(context.Background(), &authv1.ConsumeStepUpRequest{
		StepUpToken: "tok", ExpectedSubject: "u", ExpectedOrgId: "o", ExpectedSessionId: "s", ExpectedAction: "a",
	}); status.Code(err) != codes.Unavailable {
		t.Fatalf("want Unavailable, got %v", err)
	}
}

func TestRevokeOperatorSession_IncompleteFamilyID(t *testing.T) {
	t.Parallel()
	sess := &fakeSessionIssuer{
		accessProof: sessionjwt.Claims{Subject: "u", OrgID: "o", SessionID: "sid", FamilyID: "", JTI: "jti"},
	}
	srv := totpServer(t, nil, sess)
	if _, err := srv.RevokeOperatorSession(context.Background(), &authv1.RevokeOperatorSessionRequest{
		AccessToken: "access-proof", SessionId: "sid",
	}); status.Code(err) != codes.Unauthenticated {
		t.Fatalf("want Unauthenticated, got %v", err)
	}
	if sess.revokeCalls != 0 {
		t.Fatalf("revoke calls=%d", sess.revokeCalls)
	}
}
