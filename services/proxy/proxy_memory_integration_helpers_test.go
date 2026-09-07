//go:build integration

package proxy_test

import (
	"context"
	"net/http"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/grpctest"
	"github.com/Rick1330/ibex-harness/packages/contextclient"
	"github.com/Rick1330/ibex-harness/packages/logger"
	contextv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/context/v1"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

const (
	memoryIntegrationAssembleBlob = "assembled memory context blob"
	memoryIntegrationChatBody     = `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`
)

type memoryAssembleBehavior struct {
	delay         time.Duration
	errCode       codes.Code
	resp          *contextv1.AssembleContextResponse
	defaultOKResp bool
}

type configurableContextServer struct {
	contextv1.UnimplementedContextAssemblyServiceServer
	mu       sync.Mutex
	behavior memoryAssembleBehavior
	calls    int
}

func (s *configurableContextServer) setBehavior(b memoryAssembleBehavior) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.behavior = b
}

func (s *configurableContextServer) callCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.calls
}

func (s *configurableContextServer) AssembleContext(
	ctx context.Context, _ *contextv1.AssembleContextRequest,
) (*contextv1.AssembleContextResponse, error) {
	s.mu.Lock()
	b := s.behavior
	s.calls++
	s.mu.Unlock()

	if err := s.applyDelay(ctx, b.delay); err != nil {
		return nil, err
	}
	if b.errCode != codes.OK {
		return nil, status.Error(b.errCode, "injected assemble failure")
	}
	if b.resp != nil {
		return b.resp, nil
	}
	if !b.defaultOKResp {
		return &contextv1.AssembleContextResponse{}, nil
	}
	return &contextv1.AssembleContextResponse{
		AssembledContext: memoryIntegrationAssembleBlob,
		TokensUsed:       42,
		MemoriesIncluded: 3,
	}, nil
}

func (s *configurableContextServer) applyDelay(ctx context.Context, delay time.Duration) error {
	if delay <= 0 {
		return nil
	}
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return status.Error(codes.DeadlineExceeded, "assemble delayed past deadline")
	case <-timer.C:
		return nil
	}
}

type capturingMockProvider struct {
	mockForwardingProvider
	mu   sync.Mutex
	last provider.Request
}

func (p *capturingMockProvider) Complete(ctx context.Context, req provider.Request) (provider.Response, error) {
	p.mu.Lock()
	p.last = req
	p.mu.Unlock()
	return p.mockForwardingProvider.Complete(ctx, req)
}

func (p *capturingMockProvider) lastRequest() provider.Request {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.last
}

type memoryIntegrationEnv struct {
	proxyURL   string
	chatBearer string
	agentID    string
	server     *configurableContextServer
	provider   *capturingMockProvider
	client     *contextclient.Client
}

func startBufconnContextClient(t *testing.T, timeout time.Duration) (*configurableContextServer, *contextclient.Client) {
	t.Helper()
	fake := &configurableContextServer{}
	conn := grpctest.StartInsecureBufconn(t, func(srv *grpc.Server) {
		contextv1.RegisterContextAssemblyServiceServer(srv, fake)
	})
	client, err := contextclient.New(
		contextv1.NewContextAssemblyServiceClient(conn),
		timeout,
		logger.Discard("proxy"),
	)
	if err != nil {
		t.Fatalf("contextclient.New: %v", err)
	}
	return fake, client
}

func setupMemoryIntegrationEnv(t *testing.T, assembleTimeout time.Duration) memoryIntegrationEnv {
	t.Helper()
	fake, client := startBufconnContextClient(t, assembleTimeout)
	prov := &capturingMockProvider{}
	fx := setupProxyAuthFixtureWithOpts(t, proxyServerOpts{
		providers:      []provider.Provider{prov},
		contextClient:  client,
		contextEnabled: true,
	})
	return memoryIntegrationEnv{
		proxyURL:   fx.srv.URL,
		chatBearer: fx.chatBearer,
		agentID:    fx.agentA,
		server:     fake,
		provider:   prov,
		client:     client,
	}
}

func assertMemoryContextHeaders(t *testing.T, resp *http.Response, want memoryContextHeaders) {
	t.Helper()
	checks := []struct{ header, got, want string }{
		{"X-IBEX-Memories-Injected", resp.Header.Get("X-IBEX-Memories-Injected"), want.memories},
		{"X-IBEX-Context-Tokens", resp.Header.Get("X-IBEX-Context-Tokens"), want.tokens},
		{"X-IBEX-Context-Fallback", resp.Header.Get("X-IBEX-Context-Fallback"), want.fallback},
	}
	for _, c := range checks {
		if c.got != c.want {
			t.Fatalf("%s=%q want %q", c.header, c.got, c.want)
		}
	}
}

type memoryContextHeaders struct {
	memories string
	tokens   string
	fallback string
}

func assertInjectedAssembledMessages(t *testing.T, msgs []provider.Message) {
	t.Helper()
	if len(msgs) < 2 {
		t.Fatalf("messages=%+v", msgs)
	}
	if msgs[0].Role != "system" || msgs[0].Content != memoryIntegrationAssembleBlob {
		t.Fatalf("first message=%+v want system/%q", msgs[0], memoryIntegrationAssembleBlob)
	}
	if msgs[len(msgs)-1].Role != "user" || msgs[len(msgs)-1].Content != "hi" {
		t.Fatalf("last message=%+v want user/hi", msgs[len(msgs)-1])
	}
}

func assertPhase2OnlyUserMessage(t *testing.T, msgs []provider.Message) {
	t.Helper()
	if len(msgs) != 1 {
		t.Fatalf("messages=%+v want single user/hi turn", msgs)
	}
	if msgs[0].Role != "user" {
		t.Fatalf("role=%q want user", msgs[0].Role)
	}
	if msgs[0].Content != "hi" {
		t.Fatalf("content=%q want hi", msgs[0].Content)
	}
}
