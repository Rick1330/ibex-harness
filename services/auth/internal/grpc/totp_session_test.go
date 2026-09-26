package grpcserver

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type fakeTotp struct {
	beginURI string
	beginErr error
	confirm  error
	stepTok  string
	stepExp  time.Time
	stepErr  error
}

func (f *fakeTotp) BeginEnrollment(context.Context, service.BeginEnrollmentParams) (string, error) {
	return f.beginURI, f.beginErr
}
func (f *fakeTotp) ConfirmEnrollment(context.Context, service.ConfirmEnrollmentParams) error {
	return f.confirm
}
func (f *fakeTotp) CreateStepUp(context.Context, service.CreateStepUpParams) (string, time.Time, error) {
	return f.stepTok, f.stepExp, f.stepErr
}

type fakeSessionIssuer struct {
	access, refresh string
	aExp, rExp      time.Time
	issueErr        error
	refreshErr      error
	accessProof     sessionjwt.Claims
	refreshProof    sessionjwt.Claims
	accessProofErr  error
	refreshProofErr error
	revokeErr       error
	revokedSession  string
	revokedFamily   string
	revokedAccess   string
	revokeCalls     int
	consumeClaims   sessionjwt.Claims
	consumeErr      error
}

func (f *fakeSessionIssuer) IssuePair(sessionjwt.IssuePairParams) (string, string, time.Time, time.Time, error) {
	return f.access, f.refresh, f.aExp, f.rExp, f.issueErr
}
func (f *fakeSessionIssuer) RefreshPair(context.Context, sessionjwt.RefreshToken) (string, string, time.Time, time.Time, error) {
	return f.access, f.refresh, f.aExp, f.rExp, f.refreshErr
}

func (f *fakeSessionIssuer) ValidateAccess(context.Context, sessionjwt.RawToken) (sessionjwt.Claims, error) {
	return f.accessProof, f.accessProofErr
}

func (f *fakeSessionIssuer) VerifyAccessProof(token sessionjwt.RawToken) (sessionjwt.Claims, error) {
	if string(token) != "access-proof" {
		return sessionjwt.Claims{}, sessionjwt.ErrInvalidToken
	}
	return f.accessProof, f.accessProofErr
}

func (f *fakeSessionIssuer) VerifyRefreshProof(token sessionjwt.RefreshToken) (sessionjwt.Claims, error) {
	if string(token) != "refresh-proof" {
		return sessionjwt.Claims{}, sessionjwt.ErrInvalidToken
	}
	return f.refreshProof, f.refreshProofErr
}

func (f *fakeSessionIssuer) RevokeSession(_ context.Context, sessionID, familyID, accessJTI string) error {
	f.revokeCalls++
	f.revokedSession, f.revokedFamily, f.revokedAccess = sessionID, familyID, accessJTI
	return f.revokeErr
}

func (f *fakeSessionIssuer) ConsumeStepUp(context.Context, sessionjwt.RawToken, sessionjwt.StepUpExpectations) (sessionjwt.Claims, error) {
	return f.consumeClaims, f.consumeErr
}

func totpServer(t *testing.T, totp totpPort, sess sessionIssuerPort) *Server {
	t.Helper()
	srv, err := NewServer(ServerDeps{
		Validator:     &fakeTokenValidator{fn: func(context.Context, string) (*authv1.ValidateTokenResponse, error) { return nil, nil }},
		TokenService:  &fakeTokenAPI{},
		AgentService:  &fakeAgentAPI{},
		TotpService:   totp,
		SessionIssuer: sess,
		Metrics:       testAuthRegistry(),
		Log:           logger.Discard("t"),
	})
	if err != nil {
		t.Fatal(err)
	}
	return srv
}

func TestUnit_BeginTotpEnrollment_AuthzAndSuccess(t *testing.T) {
	t.Parallel()
	srvNil := totpServer(t, nil, nil)
	if _, err := srvNil.BeginTotpEnrollment(context.Background(), &authv1.BeginTotpEnrollmentRequest{}); status.Code(err) != codes.FailedPrecondition {
		t.Fatalf("nil totp: %v", err)
	}
	srv := totpServer(t, &fakeTotp{beginURI: "otpauth://totp/IBEX"}, nil)
	if _, err := srv.BeginTotpEnrollment(context.Background(), &authv1.BeginTotpEnrollmentRequest{}); status.Code(err) != codes.Unauthenticated {
		t.Fatalf("no caller: %v", err)
	}
	ctx := ContextWithCaller(context.Background(), CallerContext{OrgID: "org", UserID: "user", Permissions: 1})
	if _, err := srv.BeginTotpEnrollment(ctx, &authv1.BeginTotpEnrollmentRequest{OrgId: "other", UserId: "user"}); status.Code(err) != codes.PermissionDenied {
		t.Fatalf("wrong org: %v", err)
	}
	resp, err := srv.BeginTotpEnrollment(ctx, &authv1.BeginTotpEnrollmentRequest{OrgId: "org", UserId: "user"})
	if err != nil || resp.GetOtpauthUri() == "" {
		t.Fatalf("success: %+v err=%v", resp, err)
	}
}

func TestUnit_ConfirmAndStepUp_AndMapErr(t *testing.T) {
	t.Parallel()
	ft := &fakeTotp{stepTok: "step", stepExp: time.Now().UTC().Add(time.Minute)}
	srv := totpServer(t, ft, nil)
	ctx := ContextWithCaller(context.Background(), CallerContext{OrgID: "org", UserID: "user", Permissions: 3})
	if _, err := srv.ConfirmTotpEnrollment(ctx, &authv1.ConfirmTotpEnrollmentRequest{OrgId: "org", UserId: "user", TotpCode: "123456"}); err != nil {
		t.Fatal(err)
	}
	resp, err := srv.CreateStepUpToken(ctx, &authv1.CreateStepUpTokenRequest{OrgId: "org", UserId: "user", TotpCode: "123456"})
	if err != nil || resp.GetStepUpToken() != "step" {
		t.Fatalf("step: %+v err=%v", resp, err)
	}
	ft.confirm = service.ErrTOTPInvalidCode
	if _, err := srv.ConfirmTotpEnrollment(ctx, &authv1.ConfirmTotpEnrollmentRequest{OrgId: "org", UserId: "user", TotpCode: "bad"}); status.Code(err) != codes.Unauthenticated {
		t.Fatalf("invalid code map: %v", err)
	}
	cases := []struct {
		in   error
		want codes.Code
	}{
		{service.ErrTOTPDisabled, codes.FailedPrecondition},
		{service.ErrTOTPNotReady, codes.FailedPrecondition},
		{service.ErrSessionJWTMissing, codes.FailedPrecondition},
		{service.ErrTOTPLockedOut, codes.ResourceExhausted},
		{service.ErrTOTPUnavailable, codes.Unavailable},
		{service.ErrTOTPNotEnrolled, codes.FailedPrecondition},
		{service.ErrTOTPAlreadyDone, codes.AlreadyExists},
		{service.ErrInvalidArgument, codes.InvalidArgument},
		{errors.New("other"), codes.Internal},
	}
	for _, tc := range cases {
		if status.Code(mapTotpErr(tc.in)) != tc.want {
			t.Fatalf("%v -> %v", tc.in, mapTotpErr(tc.in))
		}
	}
}

func requireCode(t *testing.T, err error, want codes.Code, label string) {
	t.Helper()
	if status.Code(err) != want {
		t.Fatalf("%s: %v", label, err)
	}
}

func TestUnit_IssueOperatorSession_RefreshAndIssue(t *testing.T) {
	t.Parallel()
	now := time.Now().UTC()
	fi := &fakeSessionIssuer{access: "a", refresh: "r", aExp: now.Add(time.Minute), rExp: now.Add(time.Hour)}
	srv := totpServer(t, nil, fi)
	resp, err := srv.IssueOperatorSession(context.Background(), &authv1.IssueOperatorSessionRequest{RefreshToken: "old"})
	if err != nil {
		t.Fatalf("refresh: %v", err)
	}
	if resp.GetAccessToken() != "a" || resp.GetRefreshToken() != "r" {
		t.Fatalf("refresh tokens: %+v", resp)
	}
	fi.refreshErr = sessionjwt.ErrInvalidToken
	_, err = srv.IssueOperatorSession(context.Background(), &authv1.IssueOperatorSessionRequest{RefreshToken: "old"})
	requireCode(t, err, codes.Unauthenticated, "bad refresh")
	fi.refreshErr = nil
	srvNil := totpServer(t, nil, nil)
	_, err = srvNil.IssueOperatorSession(context.Background(), &authv1.IssueOperatorSessionRequest{})
	requireCode(t, err, codes.FailedPrecondition, "nil issuer")
	ctx := ContextWithCaller(context.Background(), CallerContext{OrgID: "org", UserID: "user", Permissions: 1})
	resp, err = srv.IssueOperatorSession(ctx, &authv1.IssueOperatorSessionRequest{})
	if err != nil {
		t.Fatalf("issue: %v", err)
	}
	if resp.GetAccessToken() != "a" {
		t.Fatalf("issue token: %+v", resp)
	}
	_, err = srv.IssueOperatorSession(context.Background(), &authv1.IssueOperatorSessionRequest{})
	requireCode(t, err, codes.Unauthenticated, "no caller")
	ctxEmptyUser := ContextWithCaller(context.Background(), CallerContext{OrgID: "org", UserID: "", Permissions: 1})
	_, err = srv.IssueOperatorSession(ctxEmptyUser, &authv1.IssueOperatorSessionRequest{})
	requireCode(t, err, codes.PermissionDenied, "empty user")
	fi.issueErr = errors.New("boom")
	_, err = srv.IssueOperatorSession(ctx, &authv1.IssueOperatorSessionRequest{})
	requireCode(t, err, codes.Internal, "issue fail")
}

func TestUnit_TotpHandlers_NilServiceAndAuthz(t *testing.T) {
	t.Parallel()
	srvNil := totpServer(t, nil, nil)
	ctx := ContextWithCaller(context.Background(), CallerContext{OrgID: "org", UserID: "user", Permissions: 1})
	_, err := srvNil.ConfirmTotpEnrollment(ctx, &authv1.ConfirmTotpEnrollmentRequest{OrgId: "org", UserId: "user"})
	requireCode(t, err, codes.FailedPrecondition, "nil confirm")
	_, err = srvNil.CreateStepUpToken(ctx, &authv1.CreateStepUpTokenRequest{OrgId: "org", UserId: "user"})
	requireCode(t, err, codes.FailedPrecondition, "nil stepup")
	ft := &fakeTotp{}
	srv := totpServer(t, ft, nil)
	_, err = srv.ConfirmTotpEnrollment(context.Background(), &authv1.ConfirmTotpEnrollmentRequest{})
	requireCode(t, err, codes.Unauthenticated, "confirm no caller")
	_, err = srv.CreateStepUpToken(context.Background(), &authv1.CreateStepUpTokenRequest{})
	requireCode(t, err, codes.Unauthenticated, "stepup no caller")
	_, err = srv.ConfirmTotpEnrollment(ctx, &authv1.ConfirmTotpEnrollmentRequest{OrgId: "other", UserId: "user"})
	requireCode(t, err, codes.PermissionDenied, "confirm wrong org")
	_, err = srv.CreateStepUpToken(ctx, &authv1.CreateStepUpTokenRequest{OrgId: "org", UserId: "other"})
	requireCode(t, err, codes.PermissionDenied, "stepup wrong user")
	ft.stepErr = service.ErrTOTPInvalidCode
	_, err = srv.CreateStepUpToken(ctx, &authv1.CreateStepUpTokenRequest{OrgId: "org", UserId: "user", TotpCode: "x"})
	requireCode(t, err, codes.Unauthenticated, "stepup invalid")
	ft.beginErr = service.ErrTOTPAlreadyDone
	_, err = srv.BeginTotpEnrollment(ctx, &authv1.BeginTotpEnrollmentRequest{OrgId: "org", UserId: "user"})
	requireCode(t, err, codes.AlreadyExists, "begin map")
}

func TestRevokeOperatorSession_DerivesIdentifiersFromVerifiedAccessClaims(t *testing.T) {
	t.Parallel()
	issuer := &fakeSessionIssuer{
		accessProof: sessionjwt.Claims{SessionID: "sid-a", FamilyID: "family-a", JTI: "jti-a"},
	}
	srv := totpServer(t, nil, issuer)
	_, err := srv.RevokeOperatorSession(context.Background(), &authv1.RevokeOperatorSessionRequest{
		SessionId: "sid-a", FamilyId: "family-a", AccessJti: "attacker-jti", AccessToken: "access-proof",
	})
	if err != nil {
		t.Fatal(err)
	}
	assertRevokeUsedVerifiedAccess(t, issuer)
}

func assertRevokeUsedVerifiedAccess(t *testing.T, issuer *fakeSessionIssuer) {
	t.Helper()
	if issuer.revokeCalls != 1 {
		t.Fatalf("revocation calls=%d", issuer.revokeCalls)
	}
	if issuer.revokedSession != "sid-a" || issuer.revokedFamily != "family-a" || issuer.revokedAccess != "jti-a" {
		t.Fatalf("revocation used unverified request identifiers: %+v", issuer)
	}
}

func TestRevokeOperatorSession_RejectsMismatchedRefreshProofWithoutSideEffects(t *testing.T) {
	t.Parallel()
	issuer := &fakeSessionIssuer{
		accessProof:  sessionjwt.Claims{SessionID: "sid-a", FamilyID: "family-a", JTI: "jti-a"},
		refreshProof: sessionjwt.Claims{SessionID: "sid-b", FamilyID: "family-b", JTI: "refresh-jti"},
	}
	srv := totpServer(t, nil, issuer)
	_, err := srv.RevokeOperatorSession(context.Background(), &authv1.RevokeOperatorSessionRequest{
		SessionId: "sid-a", AccessToken: "access-proof", RefreshToken: "refresh-proof",
	})
	requireCode(t, err, codes.Unauthenticated, "mismatched proofs")
	if issuer.revokeCalls != 0 {
		t.Fatalf("mismatched proofs triggered %d revocations", issuer.revokeCalls)
	}
}

func TestRevokeOperatorSession_RefreshOnlyProofSucceeds(t *testing.T) {
	t.Parallel()
	issuer := &fakeSessionIssuer{
		refreshProof: sessionjwt.Claims{SessionID: "sid-refresh", FamilyID: "family-refresh", JTI: "refresh-jti"},
	}
	srv := totpServer(t, nil, issuer)
	_, err := srv.RevokeOperatorSession(context.Background(), &authv1.RevokeOperatorSessionRequest{
		SessionId: "sid-refresh", FamilyId: "family-refresh", RefreshToken: "refresh-proof",
	})
	if err != nil {
		t.Fatalf("refresh-only logout proof: %v", err)
	}
	assertRefreshOnlyRevoke(t, issuer)
}

func assertRefreshOnlyRevoke(t *testing.T, issuer *fakeSessionIssuer) {
	t.Helper()
	if issuer.revokeCalls != 1 || issuer.revokedSession != "sid-refresh" || issuer.revokedFamily != "family-refresh" || issuer.revokedAccess != "" {
		t.Fatalf("refresh-only revocation mismatch: %+v", issuer)
	}
}

func TestRevokeOperatorSession_MissingProofIsUnauthenticated(t *testing.T) {
	t.Parallel()
	issuer := &fakeSessionIssuer{
		refreshProof: sessionjwt.Claims{SessionID: "sid-refresh", FamilyID: "family-refresh", JTI: "refresh-jti"},
	}
	srv := totpServer(t, nil, issuer)
	_, err := srv.RevokeOperatorSession(context.Background(), &authv1.RevokeOperatorSessionRequest{})
	requireCode(t, err, codes.Unauthenticated, "missing proof")
	if issuer.revokeCalls != 0 {
		t.Fatalf("missing proof triggered revocation: %+v", issuer)
	}
}

func TestRevokeOperatorSession_StoreFailureIsUnavailable(t *testing.T) {
	t.Parallel()
	issuer := &fakeSessionIssuer{
		refreshProof: sessionjwt.Claims{SessionID: "sid-refresh", FamilyID: "family-refresh", JTI: "refresh-jti"},
		revokeErr:    errors.New("redis down"),
	}
	srv := totpServer(t, nil, issuer)
	_, err := srv.RevokeOperatorSession(context.Background(), &authv1.RevokeOperatorSessionRequest{
		SessionId: "sid-refresh", RefreshToken: "refresh-proof",
	})
	requireCode(t, err, codes.Unavailable, "revocation store unavailable")
}

func TestLifecycleHandlers_ValidateAndConsumeStepUp(t *testing.T) {
	t.Parallel()
	issuer := &fakeSessionIssuer{
		accessProof:   sessionjwt.Claims{Subject: "user", OrgID: "org", SessionID: "sid", JTI: "jti", Permissions: 8},
		consumeClaims: sessionjwt.Claims{Subject: "user", OrgID: "org", SessionID: "sid", Permissions: 8},
	}
	srv := totpServer(t, nil, issuer)
	validated, err := srv.ValidateOperatorSession(context.Background(), &authv1.ValidateOperatorSessionRequest{AccessToken: "access"})
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if validated.GetSubject() != "user" || validated.GetJti() != "jti" {
		t.Fatalf("validated claims: %+v", validated)
	}
	issuer.accessProofErr = sessionjwt.ErrExpired
	_, err = srv.ValidateOperatorSession(context.Background(), &authv1.ValidateOperatorSessionRequest{AccessToken: "expired"})
	requireCode(t, err, codes.Unauthenticated, "expired access")
	issuer.accessProofErr = nil
	consumed, err := srv.ConsumeStepUp(context.Background(), &authv1.ConsumeStepUpRequest{
		StepUpToken: "step", ExpectedSubject: "user", ExpectedOrgId: "org", ExpectedSessionId: "sid",
		RequiredPermission: 8,
	})
	if err != nil || consumed.GetSubject() != "user" {
		t.Fatalf("consume: %+v err=%v", consumed, err)
	}
	issuer.consumeErr = sessionjwt.ErrInvalidToken
	_, err = srv.ConsumeStepUp(context.Background(), &authv1.ConsumeStepUpRequest{StepUpToken: "step"})
	requireCode(t, err, codes.Unauthenticated, "invalid step-up")
}
