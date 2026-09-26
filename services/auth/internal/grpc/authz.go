package grpcserver

import (
	"context"
	"crypto/subtle"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

type callerContextKey struct{}

const (
	errMsgMissingCallerContext = "missing caller context"
	errMsgInvalidRequest       = "invalid request"
	errMsgForbidden            = "forbidden"
	errMsgCreateTokenFailed    = "create token failed"
	serviceTokenMetadataKey    = "x-ibex-service-token"
)

var serviceLifecycleMethods = map[string]struct{}{
	"/ibex.auth.v1.AuthService/ValidateOperatorSession": {},
	"/ibex.auth.v1.AuthService/RevokeOperatorSession":   {},
	"/ibex.auth.v1.AuthService/ConsumeStepUp":           {},
}

// CallerContext is the authenticated PAT used for management RPCs.
type CallerContext struct {
	OrgID       string
	TokenID     string
	UserID      string
	Permissions int64
}

// ContextWithCaller attaches caller auth to ctx.
func ContextWithCaller(ctx context.Context, c CallerContext) context.Context {
	return context.WithValue(ctx, callerContextKey{}, c)
}

// CallerFromContext returns the caller context or false.
func CallerFromContext(ctx context.Context) (CallerContext, bool) {
	c, ok := ctx.Value(callerContextKey{}).(CallerContext)
	return c, ok
}

// AuthzUnaryInterceptor validates caller bearer tokens for management RPCs.
// tokenValidator is the unexported interface declared in server.go (same package).
func AuthzUnaryInterceptor(validator tokenValidator) grpc.UnaryServerInterceptor {
	return AuthzUnaryInterceptorWithServiceToken(validator, "")
}

// AuthzUnaryInterceptorWithServiceToken authenticates management RPCs with PATs
// and permits only the explicitly listed lifecycle RPCs to use the dedicated
// API-to-AuthService credential. IssueOperatorSession may use either path: PAT
// metadata is required for login, while the service credential is required for
// refresh.
func AuthzUnaryInterceptorWithServiceToken(validator tokenValidator, serviceToken string) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		if info.FullMethod == "/ibex.auth.v1.AuthService/ValidateToken" {
			return handler(ctx, req)
		}
		if serviceAuthAllowed(ctx, info.FullMethod, serviceToken) {
			return handler(ctx, req)
		}
		var err error
		ctx, err = authenticatePAT(ctx, validator)
		if err != nil {
			return nil, err
		}
		return handler(ctx, req)
	}
}

func serviceAuthAllowed(ctx context.Context, method, expected string) bool {
	return isServiceLifecycleMethod(method) && validServiceToken(ctx, expected)
}

func authenticatePAT(ctx context.Context, validator tokenValidator) (context.Context, error) {
	bearer, err := bearerFromMetadata(ctx)
	if err != nil {
		return nil, err
	}
	resp, err := validator.Validate(ctx, bearer)
	if err != nil {
		return nil, status.Error(codes.Unauthenticated, "invalid or expired token")
	}
	return ContextWithCaller(ctx, CallerContext{
		OrgID: resp.GetOrgId(), TokenID: optionalString(resp.TokenId),
		UserID: optionalString(resp.UserId), Permissions: resp.GetPermissions(),
	}), nil
}

func optionalString(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}

func isServiceLifecycleMethod(method string) bool {
	if _, ok := serviceLifecycleMethods[method]; ok {
		return true
	}
	return method == "/ibex.auth.v1.AuthService/IssueOperatorSession"
}

func validServiceToken(ctx context.Context, expected string) bool {
	if strings.TrimSpace(expected) == "" {
		return false
	}
	md, ok := metadata.FromIncomingContext(ctx)
	if !ok {
		return false
	}
	vals := md.Get(serviceTokenMetadataKey)
	if len(vals) != 1 || vals[0] == "" {
		return false
	}
	return subtle.ConstantTimeCompare([]byte(vals[0]), []byte(expected)) == 1
}

func bearerFromMetadata(ctx context.Context) (string, error) {
	md, ok := metadata.FromIncomingContext(ctx)
	if !ok {
		return "", status.Error(codes.Unauthenticated, "missing authorization metadata")
	}
	vals := md.Get("authorization")
	if len(vals) == 0 {
		return "", status.Error(codes.Unauthenticated, "missing authorization metadata")
	}
	raw := strings.TrimSpace(vals[0])
	const prefix = "Bearer "
	if len(raw) < len(prefix) || !strings.EqualFold(raw[:len(prefix)], prefix) {
		return "", status.Error(codes.Unauthenticated, "invalid authorization metadata")
	}
	bearer := strings.TrimSpace(raw[len(prefix):])
	if bearer == "" {
		return "", status.Error(codes.Unauthenticated, "invalid authorization metadata")
	}
	return bearer, nil
}

// OrgPermissionCheck scopes RequireOrgAndPermission.
type OrgPermissionCheck struct {
	OrgID    string
	Required int64
}

// RevokeTarget scopes CanRevoke.
type RevokeTarget struct {
	OrgID   string
	TokenID string
}

// RequireOrgAndPermission checks caller org and permission bit.
func RequireOrgAndPermission(ctx context.Context, check OrgPermissionCheck) error {
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return status.Error(codes.Unauthenticated, errMsgMissingCallerContext)
	}
	if caller.OrgID != check.OrgID {
		return status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	if !permissions.Has(caller.Permissions, check.Required) {
		return status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	return nil
}

// CanRevoke reports whether caller may revoke the target token.
func CanRevoke(caller CallerContext, target RevokeTarget) bool {
	if caller.OrgID != target.OrgID {
		return false
	}
	if permissions.Has(caller.Permissions, permissions.TokenRevoke) {
		return true
	}
	return caller.TokenID != "" && caller.TokenID == target.TokenID
}
