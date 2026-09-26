package grpcserver

import (
	"context"
	"errors"
	"testing"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestUnit_AssertSelfCaller_EmptyUserIDDenied(t *testing.T) {
	t.Parallel()
	srv := totpServer(t, &fakeTotp{beginURI: "otpauth://totp/IBEX"}, nil)
	ctx := ContextWithCaller(context.Background(), CallerContext{OrgID: "org", UserID: "", Permissions: 1})
	if _, err := srv.BeginTotpEnrollment(ctx, &authv1.BeginTotpEnrollmentRequest{OrgId: "org", UserId: "user"}); status.Code(err) != codes.PermissionDenied {
		t.Fatalf("empty caller user: %v", err)
	}
}

func TestRevokeOperatorSession_RejectsMismatchAndIncompleteProof(t *testing.T) {
	t.Parallel()
	sess := &fakeSessionIssuer{
		accessProof: sessionjwt.Claims{Subject: "u", OrgID: "o", SessionID: "sid", FamilyID: "fam", JTI: "jti"},
	}
	srv := totpServer(t, nil, sess)
	ctx := context.Background()
	if _, err := srv.RevokeOperatorSession(ctx, &authv1.RevokeOperatorSessionRequest{
		AccessToken: "access-proof", SessionId: "other", FamilyId: "fam",
	}); status.Code(err) != codes.Unauthenticated {
		t.Fatalf("session mismatch: %v", err)
	}
	if _, err := srv.RevokeOperatorSession(ctx, &authv1.RevokeOperatorSessionRequest{
		AccessToken: "access-proof", SessionId: "sid", FamilyId: "other",
	}); status.Code(err) != codes.Unauthenticated {
		t.Fatalf("family mismatch: %v", err)
	}
	sess.accessProof = sessionjwt.Claims{Subject: "u", OrgID: "o", SessionID: "", FamilyID: "fam", JTI: "jti"}
	if _, err := srv.RevokeOperatorSession(ctx, &authv1.RevokeOperatorSessionRequest{
		AccessToken: "access-proof", SessionId: "sid", FamilyId: "fam",
	}); status.Code(err) != codes.Unauthenticated {
		t.Fatalf("incomplete proof: %v", err)
	}
	if sess.revokeCalls != 0 {
		t.Fatalf("unexpected revoke calls: %d", sess.revokeCalls)
	}
}

func TestValidateOperatorSession_MapsNonAuthErrorsUnavailable(t *testing.T) {
	t.Parallel()
	sess := &fakeSessionIssuer{accessProofErr: errors.New("redis down")}
	srv := totpServer(t, nil, sess)
	if _, err := srv.ValidateOperatorSession(context.Background(), &authv1.ValidateOperatorSessionRequest{
		AccessToken: "access",
	}); status.Code(err) != codes.Unavailable {
		t.Fatalf("want Unavailable, got %v", err)
	}
}

func TestIssueOperatorSession_RefreshErrorMapping(t *testing.T) {
	t.Parallel()
	expired := &fakeSessionIssuer{refreshErr: sessionjwt.ErrExpired}
	srv := totpServer(t, nil, expired)
	if _, err := srv.IssueOperatorSession(context.Background(), &authv1.IssueOperatorSessionRequest{
		RefreshToken: "old",
	}); status.Code(err) != codes.Unauthenticated {
		t.Fatalf("expired refresh: %v", err)
	}
	boom := &fakeSessionIssuer{refreshErr: errors.New("boom")}
	srv = totpServer(t, nil, boom)
	if _, err := srv.IssueOperatorSession(context.Background(), &authv1.IssueOperatorSessionRequest{
		RefreshToken: "old",
	}); status.Code(err) != codes.Unavailable {
		t.Fatalf("internal refresh: %v", err)
	}
}

func TestBeginTotpEnrollment_MapsGenericServiceErrorInternal(t *testing.T) {
	t.Parallel()
	srv := totpServer(t, &fakeTotp{beginErr: errors.New("db")}, nil)
	ctx := ContextWithCaller(context.Background(), CallerContext{OrgID: "org", UserID: "user", Permissions: 1})
	if _, err := srv.BeginTotpEnrollment(ctx, &authv1.BeginTotpEnrollmentRequest{OrgId: "org", UserId: "user"}); status.Code(err) != codes.Internal {
		t.Fatalf("want Internal, got %v", err)
	}
}
