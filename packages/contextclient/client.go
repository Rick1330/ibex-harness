// Package contextclient provides a fail-open gRPC client for ContextAssemblyService.AssembleContext
// (milestone 3.5.D.1 / ADR-0071). Callers must never treat Assemble failures as LLM-path errors.
package contextclient

import (
	"context"
	"fmt"
	"reflect"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	contextv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/context/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

const defaultAssembleTimeout = 45 * time.Millisecond

// Client wraps ContextAssemblyService.AssembleContext with a per-call deadline and fail-open semantics.
type Client struct {
	client  contextv1.ContextAssemblyServiceClient
	timeout time.Duration
	log     *logger.Logger
}

// New creates a Client. timeout <= 0 defaults to 45ms (proxy assemble budget under ADR-0071).
func New(client contextv1.ContextAssemblyServiceClient, timeout time.Duration, log *logger.Logger) (*Client, error) {
	if isNilContextClient(client) {
		return nil, fmt.Errorf("contextclient: nil ContextAssemblyServiceClient")
	}
	if log == nil {
		return nil, fmt.Errorf("contextclient: nil logger")
	}
	if timeout <= 0 {
		timeout = defaultAssembleTimeout
	}
	return &Client{client: client, timeout: timeout, log: log}, nil
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
	// TODO(3.5.Dx): optional packages/circuitbreaker around Assemble — deferred from 3.5.D.1
	// (auth gRPC path has no breaker; provider path uses packages/circuitbreaker separately).
	resp, err := c.client.AssembleContext(callCtx, toProto(req))
	elapsed := time.Since(started)
	if err != nil {
		return c.fallback(callCtx, err, elapsed)
	}
	return fromProto(resp)
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
	return AssembleResult{Fallback: true, FallbackReason: reason}
}
