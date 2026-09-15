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
}

func (f *fakeSessionIssuer) IssuePair(sessionjwt.IssuePairParams) (string, string, time.Time, time.Time, error) {
	return f.access, f.refresh, f.aExp, f.rExp, f.issueErr
}
func (f *fakeSessionIssuer) RefreshPair(context.Context, string) (string, string, time.Time, time.Time, error) {
	return f.access, f.refresh, f.aExp, f.rExp, f.refreshErr
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
