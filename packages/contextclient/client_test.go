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
			if req.GetOrgId() != "org-1" || req.GetAgentId() != "agent-1" {
				t.Fatalf("unexpected ids: org=%q agent=%q", req.GetOrgId(), req.GetAgentId())
			}
			if req.GetModel() != "gpt-4o" || req.GetQuery() != "hello" {
				t.Fatalf("unexpected model/query")
			}
			if len(req.GetRecentMessages()) != 1 || req.GetRecentMessages()[0].GetContent() != "hi" {
				t.Fatalf("unexpected messages: %+v", req.GetRecentMessages())
			}
			opts := req.GetOptions()
			if opts == nil || !opts.GetSkipColdMemories() || opts.GetMaxMemories() != 3 {
				t.Fatalf("unexpected options: %+v", opts)
			}
			return &contextv1.AssembleContextResponse{
				AssembledContext: "assembled",
				TokensUsed:       10,
				MemoriesIncluded: 2,
				DirectiveTokens:  3,
				HistoryTokens:    4,
				MemoryTokens:     5,
			}, nil
		},
	}
	c, err := New(mock, 50*time.Millisecond, logger.Discard("test"))
	if err != nil {
		t.Fatal(err)
	}
	got := c.Assemble(context.Background(), AssembleParams{
		OrgID:   "org-1",
		AgentID: "agent-1",
		Model:   "gpt-4o",
		Query:   "hello",
		RecentMessages: []Message{
			{Role: "user", Content: "hi"},
		},
		Options: AssembleOptions{SkipColdMemories: true, MaxMemories: 3},
	})
	if got.Fallback {
		t.Fatalf("unexpected fallback: %+v", got)
	}
	if got.AssembledContext != "assembled" || got.TokensUsed != 10 || got.MemoriesIncluded != 2 {
		t.Fatalf("mapped fields: %+v", got)
	}
	if got.DirectiveTokens != 3 || got.HistoryTokens != 4 || got.MemoryTokens != 5 {
		t.Fatalf("token counters: %+v", got)
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
		{name: "generic", err: errors.New("boom"), want: codes.Unknown.String()},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			mock := &mockContextAssemblyServiceClient{
				assembleFn: func(context.Context, *contextv1.AssembleContextRequest, ...grpc.CallOption) (*contextv1.AssembleContextResponse, error) {
					return nil, tc.err
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
			if got.AssembledContext != "" {
				t.Fatalf("want empty assembled context on fallback, got %q", got.AssembledContext)
			}
			if got.FallbackReason != tc.want {
				t.Fatalf("FallbackReason = %q, want %q", got.FallbackReason, tc.want)
			}
		})
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
