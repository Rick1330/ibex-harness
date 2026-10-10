package http

import (
	"errors"
	"fmt"
	"strings"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/google/uuid"
	"google.golang.org/protobuf/types/known/timestamppb"
)

var (
	ErrPrincipalContextUnavailable = errors.New("principal context unavailable")
	ErrPrincipalAgentMismatch      = errors.New("principal context agent mismatch")
)

// principalContextFromVerifiedAuth maps only AuthService-verified data. It is
// additive: existing auth and agent context values remain authoritative.
func principalContextFromVerifiedAuth(result *auth.ValidateResult, agent *auth.AgentRecord, requestID, traceID, source string, now time.Time) (*authv1.PrincipalContext, error) {
	if result == nil || result.OrgID == uuid.Nil || agent == nil || agent.ID == uuid.Nil {
		return nil, ErrPrincipalContextUnavailable
	}
	if agent.OrgID != uuid.Nil && agent.OrgID != result.OrgID {
		return nil, ErrPrincipalContextUnavailable
	}
	if result.AgentID != uuid.Nil && result.AgentID != agent.ID {
		return nil, ErrPrincipalAgentMismatch
	}
	principalID := agent.ID.String()
	principalType := "service"
	if strings.TrimSpace(result.UserID) != "" {
		principalID = result.UserID
		principalType = "user"
	}
	if strings.TrimSpace(source) == "" {
		source = "proxy-auth"
	}
	if now.IsZero() {
		now = time.Now().UTC()
	}
	ctx := &authv1.PrincipalContext{
		OrgId: result.OrgID.String(), PrincipalId: principalID, AgentId: agent.ID.String(),
		PrincipalType: principalType, Authority: "AuthService", IssuedAt: timestamppb.New(now.UTC()),
		RequestId: requestID, TraceId: traceID, Source: source, Permissions: result.Permissions, TokenId: result.TokenID,
	}
	if !ctx.IssuedAt.IsValid() {
		return nil, fmt.Errorf("%w: invalid issued_at", ErrPrincipalContextUnavailable)
	}
	if !result.ExpiresAt.IsZero() {
		ctx.ExpiresAt = timestamppb.New(result.ExpiresAt.UTC())
		if !ctx.ExpiresAt.IsValid() {
			return nil, fmt.Errorf("%w: invalid expires_at", ErrPrincipalContextUnavailable)
		}
	}
	return ctx, nil
}
