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

type principalContextInput struct {
	result    *auth.ValidateResult
	agent     *auth.AgentRecord
	requestID string
	traceID   string
	source    string
	now       time.Time
}

// principalContextFromVerifiedAuth maps only AuthService-verified data. It is
// additive: existing auth and agent context values remain authoritative.
func principalContextFromVerifiedAuth(result *auth.ValidateResult, agent *auth.AgentRecord, requestID, traceID, source string, now time.Time) (*authv1.PrincipalContext, error) {
	return buildPrincipalContext(principalContextInput{
		result: result, agent: agent, requestID: requestID, traceID: traceID,
		source: source, now: now,
	})
}

func buildPrincipalContext(in principalContextInput) (*authv1.PrincipalContext, error) {
	if err := validatePrincipalBinding(in.result, in.agent); err != nil {
		return nil, err
	}
	issuedAt := normalizeIssuedAt(in.now)
	ctx := newPrincipalContext(in.result, in.agent, in.requestID, in.traceID, in.source, issuedAt)
	if !issuedAt.IsValid() {
		return nil, fmt.Errorf("%w: invalid issued_at", ErrPrincipalContextUnavailable)
	}
	if !setPrincipalExpiry(ctx, in.result.ExpiresAt) {
		return nil, fmt.Errorf("%w: invalid expires_at", ErrPrincipalContextUnavailable)
	}
	return ctx, nil
}

func validatePrincipalBinding(result *auth.ValidateResult, agent *auth.AgentRecord) error {
	if result == nil || result.OrgID == uuid.Nil || agent == nil || agent.ID == uuid.Nil {
		return ErrPrincipalContextUnavailable
	}
	if agent.OrgID != uuid.Nil && agent.OrgID != result.OrgID {
		return ErrPrincipalContextUnavailable
	}
	if result.AgentID != uuid.Nil && result.AgentID != agent.ID {
		return ErrPrincipalAgentMismatch
	}
	return nil
}

func normalizeIssuedAt(now time.Time) *timestamppb.Timestamp {
	if now.IsZero() {
		now = time.Now().UTC()
	}
	return timestamppb.New(now.UTC())
}

func newPrincipalContext(result *auth.ValidateResult, agent *auth.AgentRecord, requestID, traceID, source string, issuedAt *timestamppb.Timestamp) *authv1.PrincipalContext {
	principalID, principalType := principalIdentity(result, agent)
	return &authv1.PrincipalContext{
		OrgId: result.OrgID.String(), PrincipalId: principalID, AgentId: agent.ID.String(),
		PrincipalType: principalType, Authority: "AuthService", IssuedAt: issuedAt,
		RequestId: requestID, TraceId: traceID, Source: normalizePrincipalSource(source),
		Permissions: result.Permissions, TokenId: result.TokenID,
	}
}

func principalIdentity(result *auth.ValidateResult, agent *auth.AgentRecord) (string, string) {
	if strings.TrimSpace(result.UserID) != "" {
		return result.UserID, "user"
	}
	return agent.ID.String(), "service"
}

func normalizePrincipalSource(source string) string {
	if strings.TrimSpace(source) == "" {
		return "proxy-auth"
	}
	return source
}

func setPrincipalExpiry(ctx *authv1.PrincipalContext, expiresAt time.Time) bool {
	if expiresAt.IsZero() {
		return true
	}
	ctx.ExpiresAt = timestamppb.New(expiresAt.UTC())
	return ctx.ExpiresAt.IsValid()
}
