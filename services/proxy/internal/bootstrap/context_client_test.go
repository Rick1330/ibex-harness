package bootstrap

import (
	"context"
	"errors"
	"net"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/contextclient"
	"github.com/Rick1330/ibex-harness/packages/logger"
	contextv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/context/v1"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

// bootstrapContextToken satisfies the ADR-0096 non-empty token rule.
const bootstrapContextToken = "0123456789abcdef0123456789abcdef"

func TestUnit_SetupContextClient_DisabledBuildsNothing(t *testing.T) {
	t.Parallel()

	got, err := setupContextClient(config.Config{
		Environment:             "development",
		ContextEnabled:          false,
		ContextGRPCTarget:       "127.0.0.1:9092",
		ContextAssembleTimeout:  45 * time.Millisecond,
		ContextGRPCServiceToken: bootstrapContextToken,
	}, logger.Discard("proxy"), nil)
	if err != nil {
		t.Fatalf("setupContextClient: %v", err)
	}
	if got.client != nil || got.conn != nil {
		t.Fatalf("disabled context must build no client/conn, got %+v", got)
	}
}

func TestUnit_SetupContextClient_EmptyTarget(t *testing.T) {
	t.Parallel()

	got, err := setupContextClient(config.Config{
		Environment:            "development",
		ContextEnabled:         true,
		ContextGRPCTarget:      "",
		ContextAssembleTimeout: 45 * time.Millisecond,
	}, logger.Discard("proxy"), nil)
	if err != nil {
		t.Fatalf("setupContextClient: %v", err)
	}
	if got.client != nil || got.conn != nil {
		t.Fatalf("expected nil client/conn for empty target, got %+v", got)
	}
}

func TestUnit_SetupContextClient_RejectsEmptyToken(t *testing.T) {
	t.Parallel()

	got, err := setupContextClient(config.Config{
		Environment:            "development",
		ContextEnabled:         true,
		ContextGRPCTarget:      "127.0.0.1:9092",
		ContextAssembleTimeout: 45 * time.Millisecond,
	}, logger.Discard("proxy"), nil)
	if err == nil || !strings.Contains(err.Error(), "empty context service token") {
		t.Fatalf("setupContextClient() error=%v, want empty-token rejection", err)
	}
	if got.client != nil || got.conn != nil {
		t.Fatalf("rejected config must not leave a client/conn, got %+v", got)
	}
}

func TestUnit_SetupContextClient_DialsAndProbesUnavailableContinues(t *testing.T) {
	t.Parallel()

	got, err := setupContextClient(config.Config{
		Environment:             "development",
		ContextEnabled:          true,
		ContextGRPCTarget:       closedLoopbackAddr(t),
		ContextAssembleTimeout:  45 * time.Millisecond,
		ContextGRPCServiceToken: bootstrapContextToken,
	}, logger.Discard("proxy"), nil)
	if err != nil {
		t.Fatalf("UNAVAILABLE probe must continue startup, got %v", err)
	}
	if got.client == nil || got.conn == nil {
		t.Fatal("expected non-nil client and conn")
	}
	t.Cleanup(func() {
		if err := got.conn.Close(); err != nil {
			t.Errorf("close conn: %v", err)
		}
	})
}

func TestUnit_SetupContextClient_ProbeUnimplementedAcceptsAndPassesToken(t *testing.T) {
	t.Parallel()

	observed := make(chan []string, 1)
	addr := startStubContextServer(t, &stubContextServer{
		searchErr:     status.Error(codes.Unimplemented, "stub"),
		observedToken: observed,
	})
	got, err := setupContextClient(config.Config{
		Environment:             "development",
		ContextEnabled:          true,
		ContextGRPCTarget:       addr,
		ContextAssembleTimeout:  500 * time.Millisecond,
		ContextGRPCServiceToken: bootstrapContextToken,
	}, logger.Discard("proxy"), nil)
	if err != nil {
		t.Fatalf("UNIMPLEMENTED probe must pass startup, got %v", err)
	}
	if got.client == nil || got.conn == nil {
		t.Fatal("expected non-nil client and conn")
	}
	t.Cleanup(func() {
		if err := got.conn.Close(); err != nil {
			t.Errorf("close conn: %v", err)
		}
	})
	assertObservedToken(t, observed)
}

func TestUnit_SetupContextClient_ProbeUnauthenticatedFailsStartup(t *testing.T) {
	t.Parallel()

	observed := make(chan []string, 1)
	addr := startStubContextServer(t, &stubContextServer{
		searchErr:     status.Error(codes.Unauthenticated, "caller authentication required"),
		observedToken: observed,
	})
	got, err := setupContextClient(config.Config{
		Environment:             "development",
		ContextEnabled:          true,
		ContextGRPCTarget:       addr,
		ContextAssembleTimeout:  500 * time.Millisecond,
		ContextGRPCServiceToken: bootstrapContextToken,
	}, logger.Discard("proxy"), nil)
	if err == nil || !errors.Is(err, contextclient.ErrCallerAuthRejected) {
		t.Fatalf("setupContextClient() error=%v, want rejected caller auth", err)
	}
	if !strings.Contains(err.Error(), "IBEX_CONTEXT_GRPC_SERVICE_TOKEN") {
		t.Fatalf("error=%v must name the token env var", err)
	}
	if strings.Contains(err.Error(), bootstrapContextToken) {
		t.Fatal("error must never contain the token value")
	}
	if got.client != nil || got.conn != nil {
		t.Fatalf("rejected startup must not leave a client/conn, got %+v", got)
	}
	assertObservedToken(t, observed)
}

func TestUnit_ProbeContextCallerAuth_Classifies(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name    string
		probe   error
		wantErr bool
	}{
		{name: "passed", probe: nil},
		{name: "rejected is fatal", probe: contextclient.ErrCallerAuthRejected, wantErr: true},
		{name: "inconclusive continues", probe: contextclient.ErrCallerAuthInconclusive, wantErr: false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			err := probeContextCallerAuth(fakeCallerAuthProber{err: tc.probe}, logger.Discard("proxy"))
			if tc.wantErr && err == nil {
				t.Fatal("want startup error")
			}
			if !tc.wantErr && err != nil {
				t.Fatalf("want continue, got %v", err)
			}
		})
	}
}

type fakeCallerAuthProber struct {
	err error
}

func (f fakeCallerAuthProber) ProbeCallerAuth(context.Context) error { return f.err }

// stubContextServer answers SearchMemories with a fixed status so the probe
// classification can be exercised over a real gRPC connection.
type stubContextServer struct {
	contextv1.UnimplementedContextAssemblyServiceServer
	searchErr     error
	observedToken chan<- []string
}

func (s *stubContextServer) SearchMemories(ctx context.Context, _ *contextv1.SearchMemoriesRequest) (*contextv1.SearchMemoriesResponse, error) {
	if s.observedToken != nil {
		md, _ := metadata.FromIncomingContext(ctx)
		s.observedToken <- md.Get(contextclient.ServiceTokenMetadataKey)
	}
	if s.searchErr != nil {
		return nil, s.searchErr
	}
	return &contextv1.SearchMemoriesResponse{}, nil
}

func startStubContextServer(t *testing.T, stub *stubContextServer) string {
	t.Helper()
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	srv := grpc.NewServer()
	contextv1.RegisterContextAssemblyServiceServer(srv, stub)
	go func() {
		_ = srv.Serve(lis) //nolint:errcheck // Stop closes the listener; Serve then returns
	}()
	t.Cleanup(srv.Stop)
	return lis.Addr().String()
}

func closedLoopbackAddr(t *testing.T) string {
	t.Helper()
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	addr := lis.Addr().String()
	if err := lis.Close(); err != nil {
		t.Fatalf("close listener: %v", err)
	}
	return addr
}

func assertObservedToken(t *testing.T, observed <-chan []string) {
	t.Helper()
	select {
	case values := <-observed:
		if len(values) != 1 || values[0] != bootstrapContextToken {
			t.Fatalf("server observed token metadata %v, want exactly the configured token", values)
		}
	case <-time.After(time.Second):
		t.Fatal("context server never received the probe")
	}
}

func TestUnit_CollectGRPCConns(t *testing.T) {
	t.Parallel()

	if got := collectGRPCConns(nil, nil); len(got) != 0 {
		t.Fatalf("len=%d, want 0", len(got))
	}
}
