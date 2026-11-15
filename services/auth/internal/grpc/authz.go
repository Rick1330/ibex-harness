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
type expectedOrgContextKey struct{}

const (
	errMsgMissingCallerContext = "missing caller context"
	errMsgMissingExpectedOrg   = "missing expected org assertion"
	errMsgInvalidRequest       = "invalid request"
	errMsgForbidden            = "forbidden"
	errMsgCreateTokenFailed    = "create token failed"
	serviceTokenMetadataKey    = "x-ibex-service-token"
	expectedOrgMetadataKey     = "x-ibex-expected-org"
	issueOperatorSessionMethod = "/ibex.auth.v1.AuthService/IssueOperatorSession"
)

// orgScopedServiceMethods are the RPCs that read or mutate one org's session
// state. A service credential may call them only with an explicit org
// assertion, because the credential alone says nothing about which org the
// call is for.
var orgScopedServiceMethods = map[string]struct{}{
	"/ibex.auth.v1.AuthService/ValidateOperatorSession": {},
	"/ibex.auth.v1.AuthService/RevokeOperatorSession":   {},
	"/ibex.auth.v1.AuthService/ConsumeStepUp":           {},
}

// ServiceTokens is the pair of API-to-AuthService credentials.
//
// They are separate because they carry different authority. A single secret
// that could both mint a session and inspect, revoke, or consume a step-up
// proof for any org made every one of those calls org-blind (finding S04).
// Lifecycle authenticates ValidateOperatorSession, RevokeOperatorSession and
// ConsumeStepUp; Issue authenticates IssueOperatorSession.
//
// What the split buys: the issue credential cannot validate, revoke, or
// consume a proof, and the lifecycle credential cannot mint a session, so a
// leaked issuance secret can no longer approve a step-up and a leaked
// lifecycle secret can no longer mint sessions.
//
// What it does not buy: it is not a defence against a compromised API
// process. That process holds both values and can assert any org in
// x-ibex-expected-org, so the org assertion below converts an org-blind call
// into a refused call only when the caller states the wrong org by mistake —
// a correctness fence against the bug class, not a boundary against a
// compromised caller. Per-org credentials or mTLS caller identity are Stage 2.
type ServiceTokens struct {
	Lifecycle string
	Issue     string
}

// CallerContext is the authenticated PAT used for management RPCs.
type CallerContext struct {
	OrgID       string
	TokenID     string
	UserID      string
	AgentID     string
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
	return AuthzUnaryInterceptorWithServiceTokens(validator, ServiceTokens{})
}

// AuthzUnaryInterceptorWithServiceTokens authenticates management RPCs with
// PATs and permits only the explicitly listed lifecycle RPCs to use the
// dedicated API-to-AuthService credentials in tokens. The two credentials are
// not interchangeable: see ServiceTokens.
func AuthzUnaryInterceptorWithServiceTokens(validator tokenValidator, tokens ServiceTokens) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		if info.FullMethod == validateTokenFullMethod {
			return handler(ctx, req)
		}
		serviceCtx, ok, err := authorizeServiceCall(ctx, info.FullMethod, tokens)
		if err != nil {
			return nil, err
		}
		if ok {
			return handler(serviceCtx, req)
		}
		patCtx, err := authenticatePAT(ctx, validator)
		if err != nil {
			return nil, err
		}
		return handler(patCtx, req)
	}
}

// authorizeServiceCall reports whether the call authenticated with a service
// credential, and the context its handler must see. A credential of the wrong
// class falls through to PAT authentication, which then fails with
// UNAUTHENTICATED when no bearer is present.
func authorizeServiceCall(ctx context.Context, method string, tokens ServiceTokens) (context.Context, bool, error) {
	if isOrgScopedServiceMethod(method) && validServiceToken(ctx, tokens.Lifecycle) {
		scoped, err := withExpectedOrg(ctx)
		if err != nil {
			return nil, false, err
		}
		return scoped, true, nil
	}
	if method == issueOperatorSessionMethod && validServiceToken(ctx, tokens.Issue) {
		return ctx, true, nil
	}
	return ctx, false, nil
}

// withExpectedOrg reads the org assertion a lifecycle caller must supply and
// stores it for the handler to compare against verified claims.
func withExpectedOrg(ctx context.Context) (context.Context, error) {
	orgID, err := expectedOrgFromMetadata(ctx)
	if err != nil {
		return nil, err
	}
	return context.WithValue(ctx, expectedOrgContextKey{}, orgID), nil
}

// expectedOrgFromMetadata rejects a lifecycle service call that does not name
// the org it is acting for. Absent is refused rather than treated as "any
// org": the API is the only caller of these three methods and always knows the
// org it is handling.
func expectedOrgFromMetadata(ctx context.Context) (string, error) {
	md, ok := metadata.FromIncomingContext(ctx)
	if !ok {
		return "", status.Error(codes.PermissionDenied, errMsgMissingExpectedOrg)
	}
	vals := md.Get(expectedOrgMetadataKey)
	if len(vals) != 1 {
		return "", status.Error(codes.PermissionDenied, errMsgMissingExpectedOrg)
	}
	orgID := strings.TrimSpace(vals[0])
	if orgID == "" {
		return "", status.Error(codes.PermissionDenied, errMsgMissingExpectedOrg)
	}
	return orgID, nil
}

// ExpectedOrgFromContext returns the org a service-authenticated caller
// asserted. PAT callers have no assertion — their org comes from the token
// claims — so handlers skip the comparison for them.
func ExpectedOrgFromContext(ctx context.Context) (string, bool) {
	orgID, ok := ctx.Value(expectedOrgContextKey{}).(string)
	return orgID, ok
}

// assertExpectedOrg refuses a call whose asserted org differs from the org of
// the proof the caller presented.
func assertExpectedOrg(ctx context.Context, orgID string) error {
	expected, ok := ExpectedOrgFromContext(ctx)
	if !ok {
		return nil
	}
	if expected != orgID {
		return status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	return nil
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
		UserID: optionalString(resp.UserId), AgentID: optionalString(resp.AgentId),
		Permissions: resp.GetPermissions(),
	}), nil
}

func optionalString(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}

func isServiceLifecycleMethod(method string) bool {
	return isOrgScopedServiceMethod(method) || method == issueOperatorSessionMethod
}

func isOrgScopedServiceMethod(method string) bool {
	_, ok := orgScopedServiceMethods[method]
	return ok
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
