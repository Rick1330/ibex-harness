// Package contextclient provides a fail-open gRPC client for ContextAssemblyService.AssembleContext
// (milestone 3.5.D.1 / ADR-0071). Callers must never treat Assemble failures as LLM-path errors.
package contextclient

import (
	"context"
	"errors"
	"fmt"
	"reflect"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	contextv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/context/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

const (
	defaultAssembleTimeout = 45 * time.Millisecond

	// ServiceTokenMetadataKey is the gRPC metadata key the ContextAssemblyService
	// requires on every call (ADR-0096). It is deliberately distinct from
	// AuthService's x-ibex-service-token so one caller credential can never stand
	// in for the other.
	ServiceTokenMetadataKey = "x-ibex-context-service-token"
)

var (
	// ErrCallerAuthRejected reports UNAUTHENTICATED from the context server: the
	// service token was missing, duplicated on the wire, or did not match.
	ErrCallerAuthRejected = errors.New("context caller authentication rejected")
	// ErrCallerAuthInconclusive reports any other probe failure (UNAVAILABLE,
	// DEADLINE_EXCEEDED, unknown). Startup treats it as non-fatal.
	ErrCallerAuthInconclusive = errors.New("context caller authentication inconclusive")
)

// AssembleFallbackRecorder records fail-open Assemble outcomes (stable reason labels only).
// Single-method interface named with the Go -er convention (Record → Recorder).
type AssembleFallbackRecorder interface {
	RecordAssembleFallback(reason string)
}

// Client wraps ContextAssemblyService.AssembleContext with a per-call deadline and fail-open semantics.
type Client struct {
	client  contextv1.ContextAssemblyServiceClient
	timeout time.Duration
	log     *logger.Logger
	metrics AssembleFallbackRecorder
	// callerAuthMD is built once; it is read-only for the life of the client so
	// concurrent Assemble calls can share it without copying per call.
	callerAuthMD metadata.MD
}

// New creates a Client. timeout <= 0 defaults to 45ms (proxy assemble budget under ADR-0071).
// serviceToken is the shared secret for the x-ibex-context-service-token metadata
// entry (ADR-0096); an empty token is rejected so a client can never be built that
// the server would answer with UNAUTHENTICATED.
func New(client contextv1.ContextAssemblyServiceClient, timeout time.Duration, log *logger.Logger, serviceToken string) (*Client, error) {
	if isNilContextClient(client) {
		return nil, fmt.Errorf("contextclient: nil ContextAssemblyServiceClient")
	}
	if log == nil {
		return nil, fmt.Errorf("contextclient: nil logger")
	}
	if strings.TrimSpace(serviceToken) == "" {
		return nil, fmt.Errorf("contextclient: empty context service token")
	}
	if timeout <= 0 {
		timeout = defaultAssembleTimeout
	}
	return &Client{
		client: client, timeout: timeout, log: log,
		callerAuthMD: metadata.Pairs(ServiceTokenMetadataKey, serviceToken),
	}, nil
}

// SetAssembleFallbackRecorder attaches an optional fail-open counter (nil clears).
func (c *Client) SetAssembleFallbackRecorder(m AssembleFallbackRecorder) {
	if c == nil {
		return
	}
	c.metrics = m
}

func isNilContextClient(client contextv1.ContextAssemblyServiceClient) bool {
	if client == nil {
		return true
	}
	v := reflect.ValueOf(client)
	return v.Kind() == reflect.Pointer && v.IsNil()
}

// Assemble calls AssembleContext with a bounded deadline.
// It never surfaces a Go error to the caller: transport/status failures return Fallback=true.
func (c *Client) Assemble(ctx context.Context, req AssembleParams) AssembleResult {
	callCtx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	started := time.Now()
	// Deferred (3.5.Dx): optional packages/circuitbreaker around Assemble was scoped out of 3.5.D.1
	// (auth gRPC path has no breaker; provider path uses packages/circuitbreaker separately).
	resp, err := c.client.AssembleContext(c.callerAuthContext(callCtx), toProto(req))
	elapsed := time.Since(started)
	if err != nil {
		return c.fallback(callCtx, err, elapsed)
	}
	out := fromProto(resp)
	if out.Fallback {
		c.recordFallback(out.FallbackReason)
	}
	return out
}

// ProbeCallerAuth confirms the context server accepts this client's service
// token by calling SearchMemories with an empty request. SearchMemories is a
// stub that returns UNIMPLEMENTED after the caller guard runs (ADR-0038), so
// UNIMPLEMENTED means the token was accepted. UNAUTHENTICATED maps to
// ErrCallerAuthRejected; every other outcome maps to ErrCallerAuthInconclusive.
// Startup decides which of those is fatal. The caller owns the deadline;
// bootstrap applies a short startup budget.
func (c *Client) ProbeCallerAuth(ctx context.Context) error {
	_, err := c.client.SearchMemories(c.callerAuthContext(ctx), &contextv1.SearchMemoriesRequest{})
	if err == nil {
		return nil
	}
	code := status.Code(err)
	switch code {
	case codes.Unimplemented:
		return nil
	case codes.Unauthenticated:
		return fmt.Errorf("%w: %s", ErrCallerAuthRejected, code)
	default:
		return fmt.Errorf("%w: %s", ErrCallerAuthInconclusive, code)
	}
}

// callerAuthContext attaches exactly one service-token entry per call and
// forwards no metadata from the caller, so a duplicate token entry or a
// different service's credential (AuthService's x-ibex-service-token) can never
// reach the wire. Interceptors that add request-scoped metadata run after this.
// The metadata map is shared read-only across calls; nothing mutates it.
func (c *Client) callerAuthContext(ctx context.Context) context.Context {
	return metadata.NewOutgoingContext(ctx, c.callerAuthMD)
}

func (c *Client) fallback(callCtx context.Context, err error, elapsed time.Duration) AssembleResult {
	code := codes.Unknown
	if st, ok := status.FromError(err); ok {
		code = st.Code()
	}
	reason := code.String()
	attrs := []any{
		"grpc_code", reason,
		"elapsed_ms", elapsed.Milliseconds(),
	}
	switch code {
	case codes.DeadlineExceeded, codes.Unavailable, codes.Canceled:
		c.log.WarnCtx(callCtx, "context assemble failed; fail-open", attrs...)
	default:
		c.log.ErrorCtx(callCtx, "context assemble unexpected failure; fail-open", attrs...)
	}
	c.recordFallback(reason)
	return AssembleResult{Fallback: true, FallbackReason: reason}
}

func (c *Client) recordFallback(reason string) {
	if c == nil || c.metrics == nil {
		return
	}
	c.metrics.RecordAssembleFallback(reason)
}
