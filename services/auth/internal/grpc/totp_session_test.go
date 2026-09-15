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

func (f *fakeTotp) BeginEnrollment(context.Context, string, string, string) (string, error) {
	return f.beginURI, f.beginErr
}
func (f *fakeTotp) ConfirmEnrollment(context.Context, string, string, string) error {
	return f.confirm
}
func (f *fakeTotp) CreateStepUp(context.Context, string, string, string, int64) (string, time.Time, error) {
	return f.stepTok, f.stepExp, f.stepErr
}

type fakeSessionIssuer struct {
	access, refresh string
	aExp, rExp      time.Time
	issueErr        error
	refreshErr      error
}

func (f *fakeSessionIssuer) IssuePair(string, string, int64) (string, string, time.Time, time.Time, error) {
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

func TestUnit_IssueOperatorSession_RefreshAndIssue(t *testing.T) {
	t.Parallel()
	now := time.Now().UTC()
	fi := &fakeSessionIssuer{access: "a", refresh: "r", aExp: now.Add(time.Minute), rExp: now.Add(time.Hour)}
	srv := totpServer(t, nil, fi)
	resp, err := srv.IssueOperatorSession(context.Background(), &authv1.IssueOperatorSessionRequest{RefreshToken: "old"})
	if err != nil || resp.GetAccessToken() != "a" || resp.GetRefreshToken() != "r" {
		t.Fatalf("refresh: %+v err=%v", resp, err)
	}
	fi.refreshErr = sessionjwt.ErrInvalidToken
	if _, err := srv.IssueOperatorSession(context.Background(), &authv1.IssueOperatorSessionRequest{RefreshToken: "old"}); status.Code(err) != codes.Unauthenticated {
		t.Fatalf("bad refresh: %v", err)
	}
	fi.refreshErr = nil
	srvNil := totpServer(t, nil, nil)
	if _, err := srvNil.IssueOperatorSession(context.Background(), &authv1.IssueOperatorSessionRequest{}); status.Code(err) != codes.FailedPrecondition {
		t.Fatalf("nil issuer: %v", err)
	}
	ctx := ContextWithCaller(context.Background(), CallerContext{OrgID: "org", UserID: "user", Permissions: 1})
	resp, err = srv.IssueOperatorSession(ctx, &authv1.IssueOperatorSessionRequest{})
	if err != nil || resp.GetAccessToken() != "a" {
		t.Fatalf("issue: %+v err=%v", resp, err)
	}
	if _, err := srv.IssueOperatorSession(context.Background(), &authv1.IssueOperatorSessionRequest{}); status.Code(err) != codes.Unauthenticated {
		t.Fatalf("no caller: %v", err)
	}
	ctxEmptyUser := ContextWithCaller(context.Background(), CallerContext{OrgID: "org", UserID: "", Permissions: 1})
	if _, err := srv.IssueOperatorSession(ctxEmptyUser, &authv1.IssueOperatorSessionRequest{}); status.Code(err) != codes.PermissionDenied {
		t.Fatalf("empty user: %v", err)
	}
	fi.issueErr = errors.New("boom")
	if _, err := srv.IssueOperatorSession(ctx, &authv1.IssueOperatorSessionRequest{}); status.Code(err) != codes.Internal {
		t.Fatalf("issue fail: %v", err)
	}
}

func TestUnit_TotpHandlers_NilServiceAndAuthz(t *testing.T) {
	t.Parallel()
	srvNil := totpServer(t, nil, nil)
	ctx := ContextWithCaller(context.Background(), CallerContext{OrgID: "org", UserID: "user", Permissions: 1})
	if _, err := srvNil.ConfirmTotpEnrollment(ctx, &authv1.ConfirmTotpEnrollmentRequest{OrgId: "org", UserId: "user"}); status.Code(err) != codes.FailedPrecondition {
		t.Fatalf("nil confirm: %v", err)
	}
	if _, err := srvNil.CreateStepUpToken(ctx, &authv1.CreateStepUpTokenRequest{OrgId: "org", UserId: "user"}); status.Code(err) != codes.FailedPrecondition {
		t.Fatalf("nil stepup: %v", err)
	}
	ft := &fakeTotp{}
	srv := totpServer(t, ft, nil)
	if _, err := srv.ConfirmTotpEnrollment(context.Background(), &authv1.ConfirmTotpEnrollmentRequest{}); status.Code(err) != codes.Unauthenticated {
		t.Fatalf("confirm no caller: %v", err)
	}
	if _, err := srv.CreateStepUpToken(context.Background(), &authv1.CreateStepUpTokenRequest{}); status.Code(err) != codes.Unauthenticated {
		t.Fatalf("stepup no caller: %v", err)
	}
	if _, err := srv.ConfirmTotpEnrollment(ctx, &authv1.ConfirmTotpEnrollmentRequest{OrgId: "other", UserId: "user"}); status.Code(err) != codes.PermissionDenied {
		t.Fatalf("confirm wrong org: %v", err)
	}
	if _, err := srv.CreateStepUpToken(ctx, &authv1.CreateStepUpTokenRequest{OrgId: "org", UserId: "other"}); status.Code(err) != codes.PermissionDenied {
		t.Fatalf("stepup wrong user: %v", err)
	}
	ft.stepErr = service.ErrTOTPInvalidCode
	if _, err := srv.CreateStepUpToken(ctx, &authv1.CreateStepUpTokenRequest{OrgId: "org", UserId: "user", TotpCode: "x"}); status.Code(err) != codes.Unauthenticated {
		t.Fatalf("stepup map: %v", err)
	}
	ft.beginErr = service.ErrTOTPAlreadyDone
	if _, err := srv.BeginTotpEnrollment(ctx, &authv1.BeginTotpEnrollmentRequest{OrgId: "org", UserId: "user"}); status.Code(err) != codes.AlreadyExists {
		t.Fatalf("begin map: %v", err)
	}
}
