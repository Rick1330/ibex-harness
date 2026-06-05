package grpcserver

import (
	"context"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

type callerContextKey struct{}

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
func AuthzUnaryInterceptor(validator *token.Validator) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		if info.FullMethod == "/ibex.auth.v1.AuthService/ValidateToken" {
			return handler(ctx, req)
		}

		bearer, err := bearerFromMetadata(ctx)
		if err != nil {
			return nil, err
		}
		resp, err := validator.Validate(ctx, bearer)
		if err != nil {
			return nil, status.Error(codes.Unauthenticated, "invalid or expired token")
		}
		tokenID := ""
		if resp.TokenId != nil {
			tokenID = *resp.TokenId
		}
		userID := ""
		if resp.UserId != nil {
			userID = *resp.UserId
		}
		ctx = ContextWithCaller(ctx, CallerContext{
			OrgID:       resp.GetOrgId(),
			TokenID:     tokenID,
			UserID:      userID,
			Permissions: resp.GetPermissions(),
		})
		return handler(ctx, req)
	}
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

// RequireOrgAndPermission checks caller org and permission bit.
func RequireOrgAndPermission(ctx context.Context, orgID string, required int64) error {
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return status.Error(codes.Unauthenticated, "missing caller context")
	}
	if caller.OrgID != orgID {
		return status.Error(codes.PermissionDenied, "forbidden")
	}
	if !permissions.Has(caller.Permissions, required) {
		return status.Error(codes.PermissionDenied, "forbidden")
	}
	return nil
}

// CanRevoke reports whether caller may revoke the target token.
func CanRevoke(caller CallerContext, orgID, targetTokenID string) bool {
	if caller.OrgID != orgID {
		return false
	}
	if permissions.Has(caller.Permissions, permissions.TokenRevoke) {
		return true
	}
	return caller.TokenID != "" && caller.TokenID == targetTokenID
}
