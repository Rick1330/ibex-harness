package grpcserver

import (
	"context"
	"errors"
	"strings"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

const errMsgTOTPNotConfigured = "totp not configured"

type totpPort interface {
	BeginEnrollment(ctx context.Context, p service.BeginEnrollmentParams) (string, error)
	ConfirmEnrollment(ctx context.Context, p service.ConfirmEnrollmentParams) error
	CreateStepUp(ctx context.Context, p service.CreateStepUpParams) (string, time.Time, error)
}

type sessionIssuerPort interface {
	IssuePair(p sessionjwt.IssuePairParams) (access, refresh string, accessExp, refreshExp time.Time, err error)
	RefreshPair(ctx context.Context, refreshToken sessionjwt.RefreshToken) (access, refresh string, accessExp, refreshExp time.Time, err error)
}

type lifecycleIssuerPort interface {
	ValidateAccess(ctx context.Context, accessToken sessionjwt.RawToken) (sessionjwt.Claims, error)
	RevokeSession(ctx context.Context, sessionID, familyID, accessJTI string) error
	ConsumeStepUp(ctx context.Context, token sessionjwt.RawToken, expect sessionjwt.StepUpExpectations) (sessionjwt.Claims, error)
}

func (s *Server) requireTotpSelf(ctx context.Context, orgID, userID string) (CallerContext, error) {
	if s.totpService == nil {
		return CallerContext{}, status.Error(codes.FailedPrecondition, errMsgTOTPNotConfigured)
	}
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return CallerContext{}, status.Error(codes.Unauthenticated, errMsgMissingCallerContext)
	}
	if err := assertSelfCaller(caller, orgID, userID); err != nil {
		return CallerContext{}, err
	}
	return caller, nil
}

func assertSelfCaller(caller CallerContext, orgID, userID string) error {
	if caller.OrgID != orgID {
		return status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	if caller.UserID == "" {
		return status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	if caller.UserID != userID {
		return status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	return nil
}

func (s *Server) totpSelfIDs(ctx context.Context, orgID, userID string) (CallerContext, error) {
	return s.requireTotpSelf(ctx, orgID, userID)
}

func (s *Server) BeginTotpEnrollment(
	ctx context.Context,
	req *authv1.BeginTotpEnrollmentRequest,
) (*authv1.BeginTotpEnrollmentResponse, error) {
	orgID, userID := req.GetOrgId(), req.GetUserId()
	if _, err := s.requireTotpSelf(ctx, orgID, userID); err != nil {
		return nil, err
	}
	uri, err := s.totpService.BeginEnrollment(ctx, service.BeginEnrollmentParams{
		OrgID: service.OrgID(orgID), UserID: service.UserID(userID), AccountName: userID,
	})
	if err != nil {
		return nil, mapTotpErr(err)
	}
	return &authv1.BeginTotpEnrollmentResponse{OtpauthUri: uri}, nil
}

func (s *Server) ConfirmTotpEnrollment(
	ctx context.Context,
	req *authv1.ConfirmTotpEnrollmentRequest,
) (*authv1.ConfirmTotpEnrollmentResponse, error) {
	if err := s.confirmTotpEnrollment(ctx, req); err != nil {
		return nil, err
	}
	return &authv1.ConfirmTotpEnrollmentResponse{}, nil
}

func (s *Server) confirmTotpEnrollment(ctx context.Context, req *authv1.ConfirmTotpEnrollmentRequest) error {
	if _, err := s.requireTotpSelf(ctx, req.GetOrgId(), req.GetUserId()); err != nil {
		return err
	}
	if err := s.totpService.ConfirmEnrollment(ctx, service.ConfirmEnrollmentParams{
		OrgID: service.OrgID(req.GetOrgId()), UserID: service.UserID(req.GetUserId()), Code: req.GetTotpCode(),
	}); err != nil {
		return mapTotpErr(err)
	}
	return nil
}

func (s *Server) CreateStepUpToken(
	ctx context.Context,
	req *authv1.CreateStepUpTokenRequest,
) (*authv1.CreateStepUpTokenResponse, error) {
	caller, err := s.totpSelfIDs(ctx, req.GetOrgId(), req.GetUserId())
	if err != nil {
		return nil, err
	}
	token, exp, err := s.totpService.CreateStepUp(ctx, service.CreateStepUpParams{
		OrgID: service.OrgID(req.GetOrgId()), UserID: service.UserID(req.GetUserId()), Code: req.GetTotpCode(), Permissions: caller.Permissions,
		SessionID: req.GetSessionId(), Action: req.GetAction(),
	})
	if err != nil {
		return nil, mapTotpErr(err)
	}
	return &authv1.CreateStepUpTokenResponse{
		StepUpToken: token,
		ExpiresAt:   timestamppb.New(exp),
	}, nil
}

func (s *Server) IssueOperatorSession(
	ctx context.Context,
	req *authv1.IssueOperatorSessionRequest,
) (*authv1.IssueOperatorSessionResponse, error) {
	if s.sessionIssuer == nil {
		return nil, status.Error(codes.FailedPrecondition, "session jwt issuer not configured")
	}
	if rt := strings.TrimSpace(req.GetRefreshToken()); rt != "" {
		return s.issueFromRefresh(ctx, rt)
	}
	return s.issueFromCaller(ctx)
}

func (s *Server) ValidateOperatorSession(ctx context.Context, req *authv1.ValidateOperatorSessionRequest) (*authv1.ValidateOperatorSessionResponse, error) {
	if s.sessionIssuer == nil {
		return nil, status.Error(codes.FailedPrecondition, "session jwt issuer not configured")
	}
	issuer, ok := s.sessionIssuer.(lifecycleIssuerPort)
	if !ok {
		return nil, status.Error(codes.FailedPrecondition, "session lifecycle not configured")
	}
	claims, err := issuer.ValidateAccess(ctx, sessionjwt.RawToken(req.GetAccessToken()))
	if err != nil {
		return nil, mapSessionValidationErr(err)
	}
	return &authv1.ValidateOperatorSessionResponse{Subject: claims.Subject, OrgId: claims.OrgID, Permissions: claims.Permissions, SessionId: claims.SessionID, Jti: claims.JTI}, nil
}

func (s *Server) RevokeOperatorSession(ctx context.Context, req *authv1.RevokeOperatorSessionRequest) (*authv1.RevokeOperatorSessionResponse, error) {
	if s.sessionIssuer == nil {
		return nil, status.Error(codes.FailedPrecondition, "session jwt issuer not configured")
	}
	if strings.TrimSpace(req.GetSessionId()) == "" {
		return nil, status.Error(codes.InvalidArgument, errMsgInvalidRequest)
	}
	issuer, ok := s.sessionIssuer.(lifecycleIssuerPort)
	if !ok {
		return nil, status.Error(codes.FailedPrecondition, "session lifecycle not configured")
	}
	if err := issuer.RevokeSession(ctx, req.GetSessionId(), req.GetFamilyId(), req.GetAccessJti()); err != nil {
		return nil, status.Error(codes.Unavailable, "session revocation unavailable")
	}
	return &authv1.RevokeOperatorSessionResponse{}, nil
}

func (s *Server) ConsumeStepUp(ctx context.Context, req *authv1.ConsumeStepUpRequest) (*authv1.ConsumeStepUpResponse, error) {
	if s.sessionIssuer == nil {
		return nil, status.Error(codes.FailedPrecondition, "session jwt issuer not configured")
	}
	issuer, ok := s.sessionIssuer.(lifecycleIssuerPort)
	if !ok {
		return nil, status.Error(codes.FailedPrecondition, "session lifecycle not configured")
	}
	claims, err := issuer.ConsumeStepUp(ctx, sessionjwt.RawToken(req.GetStepUpToken()), sessionjwt.StepUpExpectations{Subject: req.GetExpectedSubject(), OrgID: req.GetExpectedOrgId(), SessionID: req.GetExpectedSessionId(), Action: req.GetExpectedAction(), RequiredPermission: req.GetRequiredPermission()})
	if err != nil {
		return nil, mapSessionValidationErr(err)
	}
	return &authv1.ConsumeStepUpResponse{Subject: claims.Subject, OrgId: claims.OrgID, SessionId: claims.SessionID, Action: claims.Action, Permissions: claims.Permissions}, nil
}

func mapSessionValidationErr(err error) error {
	if errors.Is(err, sessionjwt.ErrExpired) || errors.Is(err, sessionjwt.ErrInvalidToken) {
		return status.Error(codes.Unauthenticated, "invalid session")
	}
	return status.Error(codes.Unavailable, "session state unavailable")
}

func (s *Server) issueFromRefresh(ctx context.Context, refreshToken string) (*authv1.IssueOperatorSessionResponse, error) {
	access, refresh, accessExp, refreshExp, err := s.sessionIssuer.RefreshPair(ctx, sessionjwt.RefreshToken(refreshToken))
	if err != nil {
		return nil, mapRefreshPairErr(err)
	}
	return &authv1.IssueOperatorSessionResponse{
		AccessToken:      access,
		RefreshToken:     refresh,
		AccessExpiresAt:  timestamppb.New(accessExp),
		RefreshExpiresAt: timestamppb.New(refreshExp),
	}, nil
}

func mapRefreshPairErr(err error) error {
	if errors.Is(err, sessionjwt.ErrInvalidToken) || errors.Is(err, sessionjwt.ErrExpired) {
		return status.Error(codes.Unauthenticated, "invalid refresh token")
	}
	return status.Error(codes.Unavailable, "refresh unavailable")
}

func (s *Server) issueFromCaller(ctx context.Context) (*authv1.IssueOperatorSessionResponse, error) {
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return nil, status.Error(codes.Unauthenticated, errMsgMissingCallerContext)
	}
	if caller.UserID == "" {
		return nil, status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	access, refresh, accessExp, refreshExp, err := s.sessionIssuer.IssuePair(sessionjwt.IssuePairParams{
		Subject: sessionjwt.Subject(caller.UserID), OrgID: sessionjwt.OrgID(caller.OrgID), Permissions: caller.Permissions,
	})
	if err != nil {
		return nil, status.Error(codes.Internal, "issue session failed")
	}
	return &authv1.IssueOperatorSessionResponse{
		AccessToken:      access,
		RefreshToken:     refresh,
		AccessExpiresAt:  timestamppb.New(accessExp),
		RefreshExpiresAt: timestamppb.New(refreshExp),
	}, nil
}

func mapTotpErr(err error) error {
	if mapped := mapTotpClientErr(err); mapped != nil {
		return mapped
	}
	if mapped := mapTotpStateErr(err); mapped != nil {
		return mapped
	}
	return status.Error(codes.Internal, "totp operation failed")
}

func mapTotpClientErr(err error) error {
	switch {
	case errors.Is(err, service.ErrTOTPInvalidCode):
		return status.Error(codes.Unauthenticated, "invalid totp code")
	case errors.Is(err, service.ErrTOTPLockedOut):
		return status.Error(codes.ResourceExhausted, "totp attempt limit exceeded")
	case errors.Is(err, service.ErrTOTPUnavailable):
		return status.Error(codes.Unavailable, "totp attempt store unavailable")
	case errors.Is(err, service.ErrInvalidArgument):
		return status.Error(codes.InvalidArgument, errMsgInvalidRequest)
	default:
		return nil
	}
}

func mapTotpStateErr(err error) error {
	switch {
	case errors.Is(err, service.ErrTOTPDisabled),
		errors.Is(err, service.ErrTOTPNotReady),
		errors.Is(err, service.ErrSessionJWTMissing):
		return status.Error(codes.FailedPrecondition, errMsgTOTPNotConfigured)
	case errors.Is(err, service.ErrTOTPNotEnrolled):
		return status.Error(codes.FailedPrecondition, "totp not enrolled")
	case errors.Is(err, service.ErrTOTPAlreadyDone):
		return status.Error(codes.AlreadyExists, "totp already confirmed")
	default:
		return nil
	}
}

// Ensure sessionjwt.Issuer satisfies sessionIssuerPort.
var _ sessionIssuerPort = (*sessionjwt.Issuer)(nil)
