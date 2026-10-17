package auth

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/Rick1330/ibex-harness/packages/policysnapshot"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

var (
	// ErrPolicySnapshotDenied indicates AuthService refused to mint a snapshot
	// for the caller's token/agent binding.
	ErrPolicySnapshotDenied = errors.New("policy snapshot denied")
	// ErrPolicySnapshotUnavailable indicates the issuance RPC could not be
	// completed (unreachable, timeout, malformed response).
	ErrPolicySnapshotUnavailable = errors.New("policy snapshot unavailable")
)

// PolicySnapshotFetcher mints a signed policy snapshot for the authenticated
// caller. Implementations forward the caller bearer to AuthService.
type PolicySnapshotFetcher interface {
	Issue(ctx context.Context, bearer, agentID string) (*policysnapshot.Envelope, error)
}

// GRPCPolicySnapshotClient calls AuthService.IssuePolicySnapshot with a
// bounded per-call deadline and forwarded bearer token.
type GRPCPolicySnapshotClient struct {
	client  authv1.AuthServiceClient
	timeout time.Duration
}

// NewGRPCPolicySnapshotClient creates a policy snapshot client.
func NewGRPCPolicySnapshotClient(client authv1.AuthServiceClient, timeout time.Duration) (*GRPCPolicySnapshotClient, error) {
	if isNilAuthClient(client) {
		return nil, fmt.Errorf("auth: nil AuthServiceClient for policy snapshot client")
	}
	if timeout <= 0 {
		timeout = 50 * time.Millisecond
	}
	return &GRPCPolicySnapshotClient{client: client, timeout: timeout}, nil
}

// Issue calls IssuePolicySnapshot with a bounded deadline and bearer metadata.
func (c *GRPCPolicySnapshotClient) Issue(ctx context.Context, bearer, agentID string) (*policysnapshot.Envelope, error) {
	callCtx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	md := metadata.Pairs("authorization", "Bearer "+bearer)
	callCtx = metadata.NewOutgoingContext(callCtx, md)

	resp, err := c.client.IssuePolicySnapshot(callCtx, &authv1.IssuePolicySnapshotRequest{AgentId: agentID})
	if err != nil {
		return nil, mapIssuePolicySnapshotError(err)
	}
	env := resp.GetEnvelope()
	if env == nil || len(env.GetPayload()) == 0 || len(env.GetSignature()) == 0 || env.GetAlgorithm() == "" || env.GetKeyId() == "" {
		return nil, ErrPolicySnapshotUnavailable
	}
	return &policysnapshot.Envelope{
		Algorithm: env.GetAlgorithm(),
		KeyID:     env.GetKeyId(),
		Payload:   env.GetPayload(),
		Signature: env.GetSignature(),
	}, nil
}

func mapIssuePolicySnapshotError(err error) error {
	switch status.Code(err) {
	case codes.Unauthenticated:
		return ErrInvalidToken
	case codes.PermissionDenied, codes.InvalidArgument, codes.FailedPrecondition:
		return ErrPolicySnapshotDenied
	default:
		return ErrPolicySnapshotUnavailable
	}
}
