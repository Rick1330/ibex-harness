package contextclient

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	contextv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/context/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type mockContextAssemblyServiceClient struct {
	assembleFn func(context.Context, *contextv1.AssembleContextRequest, ...grpc.CallOption) (*contextv1.AssembleContextResponse, error)
}

func (m *mockContextAssemblyServiceClient) AssembleContext(ctx context.Context, req *contextv1.AssembleContextRequest, opts ...grpc.CallOption) (*contextv1.AssembleContextResponse, error) {
	if m.assembleFn != nil {
		return m.assembleFn(ctx, req, opts...)
	}
	return nil, status.Error(codes.Unimplemented, "not configured")
}

func (m *mockContextAssemblyServiceClient) SearchMemories(context.Context, *contextv1.SearchMemoriesRequest, ...grpc.CallOption) (*contextv1.SearchMemoriesResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not used")
}

func (m *mockContextAssemblyServiceClient) RecordMemoryFeedback(context.Context, *contextv1.RecordMemoryFeedbackRequest, ...grpc.CallOption) (*contextv1.RecordMemoryFeedbackResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not used")
}

func TestNew_rejectsNil(t *testing.T) {
	t.Parallel()
	if _, err := New(nil, time.Millisecond, logger.Discard("test")); err == nil {
		t.Fatal("expected error for nil client")
	}
	if _, err := New(&mockContextAssemblyServiceClient{}, time.Millisecond, nil); err == nil {
		t.Fatal("expected error for nil logger")
	}
}

func TestNew_defaultTimeout(t *testing.T) {
	t.Parallel()
	c, err := New(&mockContextAssemblyServiceClient{}, 0, logger.Discard("test"))
	if err != nil {
		t.Fatal(err)
	}
	if c.timeout != defaultAssembleTimeout {
		t.Fatalf("timeout = %v, want %v", c.timeout, defaultAssembleTimeout)
	}
}

func TestAssemble_success(t *testing.T) {
	t.Parallel()
	mock := &mockContextAssemblyServiceClient{
		assembleFn: func(_ context.Context, req *contextv1.AssembleContextRequest, _ ...grpc.CallOption) (*contextv1.AssembleContextResponse, error) {
			assertSuccessAssembleRequest(t, req)
			return successAssembleResponse(), nil
		},
	}
	c, err := New(mock, 50*time.Millisecond, logger.Discard("test"))
	if err != nil {
		t.Fatal(err)
	}
	assertSuccessAssembleResult(t, c.Assemble(context.Background(), successAssembleParams()))
}

func successAssembleParams() AssembleParams {
	return AssembleParams{
		OrgID:   "org-1",
		AgentID: "agent-1",
		Model:   "gpt-4o",
		Query:   "hello",
		RecentMessages: []Message{
			{Role: "user", Content: "hi"},
		},
		Options: AssembleOptions{SkipColdMemories: true, MaxMemories: 3},
	}
}

func successAssembleResponse() *contextv1.AssembleContextResponse {
	return &contextv1.AssembleContextResponse{
		AssembledContext: "assembled",
		TokensUsed:       10,
		MemoriesIncluded: 2,
		DirectiveTokens:  3,
		HistoryTokens:    4,
		MemoryTokens:     5,
	}
}

func assertStringField(t *testing.T, got, want, field string) {
	t.Helper()
	if got != want {
		t.Fatalf("%s = %q, want %q", field, got, want)
	}
}

func assertSuccessAssembleRequest(t *testing.T, req *contextv1.AssembleContextRequest) {
	t.Helper()
	assertStringField(t, req.GetOrgId(), "org-1", "org_id")
	assertStringField(t, req.GetAgentId(), "agent-1", "agent_id")
	assertStringField(t, req.GetModel(), "gpt-4o", "model")
	assertStringField(t, req.GetQuery(), "hello", "query")
	assertSuccessRecentMessages(t, req.GetRecentMessages())
	assertSuccessOptions(t, req.GetOptions())
}

func assertSuccessRecentMessages(t *testing.T, msgs []*contextv1.Message) {
	t.Helper()
	if len(msgs) != 1 {
		t.Fatalf("recent_messages len = %d, want 1", len(msgs))
	}
	assertStringField(t, msgs[0].GetContent(), "hi", "recent_messages[0].content")
}

func assertSuccessOptions(t *testing.T, opts *contextv1.AssemblyOptions) {
	t.Helper()
	if opts == nil {
		t.Fatal("options is nil")
	}
	if !opts.GetSkipColdMemories() {
		t.Fatal("SkipColdMemories = false, want true")
	}
	if opts.GetMaxMemories() != 3 {
		t.Fatalf("MaxMemories = %d, want 3", opts.GetMaxMemories())
	}
}

func assertSuccessAssembleResult(t *testing.T, got AssembleResult) {
	t.Helper()
	if got.Fallback {
		t.Fatalf("unexpected fallback: %+v", got)
	}
	assertStringField(t, got.AssembledContext, "assembled", "AssembledContext")
	assertInt32Field(t, got.TokensUsed, 10, "TokensUsed")
	assertInt32Field(t, got.MemoriesIncluded, 2, "MemoriesIncluded")
	assertInt32Field(t, got.DirectiveTokens, 3, "DirectiveTokens")
	assertInt32Field(t, got.HistoryTokens, 4, "HistoryTokens")
	assertInt32Field(t, got.MemoryTokens, 5, "MemoryTokens")
}

func assertInt32Field(t *testing.T, got, want int32, field string) {
	t.Helper()
	if got != want {
		t.Fatalf("%s = %d, want %d", field, got, want)
	}
}

func TestAssemble_failOpenStatusCodes(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		err  error
		want string
	}{
		{name: "deadline", err: status.Error(codes.DeadlineExceeded, "slow"), want: codes.DeadlineExceeded.String()},
		{name: "unavailable", err: status.Error(codes.Unavailable, "down"), want: codes.Unavailable.String()},
		{name: "canceled", err: status.Error(codes.Canceled, "bye"), want: codes.Canceled.String()},
		{name: "invalid_argument", err: status.Error(codes.InvalidArgument, "bad"), want: codes.InvalidArgument.String()},
		{name: "unimplemented", err: status.Error(codes.Unimplemented, "nope"), want: codes.Unimplemented.String()},
		{name: "generic", err: errors.New("boom"), want: codes.Unknown.String()},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			assertFailOpen(t, tc.err, tc.want)
		})
	}
}

func assertFailOpen(t *testing.T, rpcErr error, wantReason string) {
	t.Helper()
	mock := &mockContextAssemblyServiceClient{
		assembleFn: func(context.Context, *contextv1.AssembleContextRequest, ...grpc.CallOption) (*contextv1.AssembleContextResponse, error) {
			return nil, rpcErr
		},
	}
	c, err := New(mock, 50*time.Millisecond, logger.Discard("test"))
	if err != nil {
		t.Fatal(err)
	}
	got := c.Assemble(context.Background(), AssembleParams{OrgID: "o", AgentID: "a", Model: "m", Query: "q"})
	if !got.Fallback {
		t.Fatalf("want Fallback=true, got %+v", got)
	}
	assertStringField(t, got.AssembledContext, "", "AssembledContext")
	assertStringField(t, got.FallbackReason, wantReason, "FallbackReason")
}

func TestAssemble_nilResponseFallback(t *testing.T) {
	t.Parallel()
	mock := &mockContextAssemblyServiceClient{
		assembleFn: func(context.Context, *contextv1.AssembleContextRequest, ...grpc.CallOption) (*contextv1.AssembleContextResponse, error) {
			return nil, nil
		},
	}
	c, err := New(mock, 50*time.Millisecond, logger.Discard("test"))
	if err != nil {
		t.Fatal(err)
	}
	got := c.Assemble(context.Background(), AssembleParams{OrgID: "o", AgentID: "a", Model: "m", Query: "q"})
	if !got.Fallback {
		t.Fatalf("want Fallback=true for nil response, got %+v", got)
	}
	assertStringField(t, got.FallbackReason, "nil_response", "FallbackReason")
}

type countingFallbackRecorder struct {
	reasons []string
}

func (m *countingFallbackRecorder) RecordAssembleFallback(reason string) {
	m.reasons = append(m.reasons, reason)
}

func TestAssemble_recordsFallbackMetric(t *testing.T) {
	t.Parallel()
	mock := &mockContextAssemblyServiceClient{
		assembleFn: func(context.Context, *contextv1.AssembleContextRequest, ...grpc.CallOption) (*contextv1.AssembleContextResponse, error) {
			return nil, status.Error(codes.Unavailable, "down")
		},
	}
	c, err := New(mock, 50*time.Millisecond, logger.Discard("test"))
	if err != nil {
		t.Fatal(err)
	}
	m := &countingFallbackRecorder{}
	c.SetAssembleFallbackRecorder(m)
	_ = c.Assemble(context.Background(), AssembleParams{OrgID: "o", AgentID: "a", Model: "m", Query: "q"})
	if len(m.reasons) != 1 || m.reasons[0] != codes.Unavailable.String() {
		t.Fatalf("metrics = %#v, want one Unavailable", m.reasons)
	}
}

func TestAssemble_timeout(t *testing.T) {
	t.Parallel()
	started := make(chan struct{})
	mock := &mockContextAssemblyServiceClient{
		assembleFn: func(ctx context.Context, _ *contextv1.AssembleContextRequest, _ ...grpc.CallOption) (*contextv1.AssembleContextResponse, error) {
			close(started)
			select {
			case <-ctx.Done():
				return nil, status.Error(codes.DeadlineExceeded, ctx.Err().Error())
			case <-time.After(2 * time.Second):
				return &contextv1.AssembleContextResponse{AssembledContext: "late"}, nil
			}
		},
	}
	c, err := New(mock, 20*time.Millisecond, logger.Discard("test"))
	if err != nil {
		t.Fatal(err)
	}
	begin := time.Now()
	got := c.Assemble(context.Background(), AssembleParams{OrgID: "o", AgentID: "a", Model: "m", Query: "q"})
	elapsed := time.Since(begin)
	select {
	case <-started:
	default:
		t.Fatal("mock was not invoked")
	}
	if !got.Fallback {
		t.Fatalf("want fallback on timeout, got %+v", got)
	}
	if elapsed > 200*time.Millisecond {
		t.Fatalf("elapsed %v exceeds timeout + slack", elapsed)
	}
}
