package bootstrap

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
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

// contextTestConfig is an enabled development context client aimed at target.
func contextTestConfig(target, token string) config.Config {
	return config.Config{
		Environment:             "development",
		ContextEnabled:          true,
		ContextGRPCTarget:       target,
		ContextAssembleTimeout:  45 * time.Millisecond,
		ContextGRPCServiceToken: token,
	}
}

// contextProbeConfig is contextTestConfig with the longer wall a live probe needs.
func contextProbeConfig(target string) config.Config {
	cfg := contextTestConfig(target, bootstrapContextToken)
	cfg.ContextAssembleTimeout = 500 * time.Millisecond
	return cfg
}

// requireContextClient asserts a live client/conn pair and closes the conn at cleanup.
func requireContextClient(t *testing.T, got contextClients) {
	t.Helper()
	if got.client == nil || got.conn == nil {
		t.Fatal("expected non-nil client and conn")
	}
	t.Cleanup(func() {
		if err := got.conn.Close(); err != nil {
			t.Errorf("close conn: %v", err)
		}
	})
}

// requireNoContextClient asserts the setup left nothing dialled.
func requireNoContextClient(t *testing.T, got contextClients, what string) {
	t.Helper()
	if got.client != nil || got.conn != nil {
		t.Fatalf("%s must build no client/conn, got %+v", what, got)
	}
}

func TestUnit_SetupContextClient_DisabledBuildsNothing(t *testing.T) {
	t.Parallel()

	cfg := contextTestConfig("127.0.0.1:9092", bootstrapContextToken)
	cfg.ContextEnabled = false
	got, err := setupContextClient(cfg, logger.Discard("proxy"), nil)
	if err != nil {
		t.Fatalf("setupContextClient: %v", err)
	}
	requireNoContextClient(t, got, "disabled context")
}

func TestUnit_SetupContextClient_EmptyTarget(t *testing.T) {
	t.Parallel()

	got, err := setupContextClient(contextTestConfig("", ""), logger.Discard("proxy"), nil)
	if err != nil {
		t.Fatalf("setupContextClient: %v", err)
	}
	requireNoContextClient(t, got, "empty target")
}

func TestUnit_SetupContextClient_RejectsEmptyToken(t *testing.T) {
	t.Parallel()

	got, err := setupContextClient(contextTestConfig("127.0.0.1:9092", ""), logger.Discard("proxy"), nil)
	if err == nil || !strings.Contains(err.Error(), "empty context service token") {
		t.Fatalf("setupContextClient() error=%v, want empty-token rejection", err)
	}
	requireNoContextClient(t, got, "rejected config")
}

func TestUnit_SetupContextClient_DialsAndProbesUnavailableContinues(t *testing.T) {
	t.Parallel()

	cfg := contextTestConfig(closedLoopbackAddr(t), bootstrapContextToken)
	got, err := setupContextClient(cfg, logger.Discard("proxy"), nil)
	if err != nil {
		t.Fatalf("UNAVAILABLE probe must continue startup, got %v", err)
	}
	requireContextClient(t, got)
}

func TestUnit_SetupContextClient_ProbeUnimplementedContinuesButUnproven(t *testing.T) {
	t.Parallel()

	addr, observed := stubContextProbe(t, status.Error(codes.Unimplemented, "stub"))
	got, err := setupContextClient(contextProbeConfig(addr), logger.Discard("proxy"), nil)
	if err != nil {
		t.Fatalf("UNIMPLEMENTED probe must pass startup, got %v", err)
	}
	requireContextClient(t, got)
	assertObservedToken(t, observed)
}

// TestUnit_SetupContextClient_NoGuardAnywhereDoesNotClaimVerifiedBoundary pins
// finding N2: a server with no caller guard at all answers UNIMPLEMENTED exactly
// like the guarded stub, so the startup log must warn that the boundary is
// unproven instead of reporting it verified. The documented proxy-first rollout
// reaches this state on purpose.
func TestUnit_SetupContextClient_NoGuardAnywhereDoesNotClaimVerifiedBoundary(t *testing.T) {
	t.Parallel()

	var logs bytes.Buffer
	log, err := logger.New(logger.Config{Service: "proxy", Level: slog.LevelDebug, Writer: &logs})
	if err != nil {
		t.Fatalf("logger: %v", err)
	}
	// UnimplementedContextAssemblyServiceServer installs no guard: every RPC,
	// SearchMemories included, answers UNIMPLEMENTED.
	addr := startStubContextServer(t, &contextv1.UnimplementedContextAssemblyServiceServer{})
	got, err := setupContextClient(contextProbeConfig(addr), log, nil)
	if err != nil {
		t.Fatalf("unguarded UNIMPLEMENTED probe must not fail startup, got %v", err)
	}
	requireContextClient(t, got)
	output := logs.String()
	if strings.Contains(output, "probe passed") {
		t.Fatalf("log claims the caller-auth boundary is verified:\n%s", output)
	}
	for _, want := range []string{"unproven", "does not prove"} {
		if !strings.Contains(output, want) {
			t.Fatalf("log must contain %q:\n%s", want, output)
		}
	}
	if strings.Contains(output, bootstrapContextToken) {
		t.Fatal("log must never contain the token value")
	}
}

func TestUnit_SetupContextClient_ProbeUnauthenticatedFailsStartup(t *testing.T) {
	t.Parallel()

	addr, observed := stubContextProbe(t, status.Error(codes.Unauthenticated, "caller authentication required"))
	got, err := setupContextClient(contextProbeConfig(addr), logger.Discard("proxy"), nil)
	if err == nil || !errors.Is(err, contextclient.ErrCallerAuthRejected) {
		t.Fatalf("setupContextClient() error=%v, want rejected caller auth", err)
	}
	if !strings.Contains(err.Error(), "IBEX_CONTEXT_GRPC_SERVICE_TOKEN") {
		t.Fatalf("error=%v must name the token env var", err)
	}
	if strings.Contains(err.Error(), bootstrapContextToken) {
		t.Fatal("error must never contain the token value")
	}
	requireNoContextClient(t, got, "rejected startup")
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
		{name: "unproven continues", probe: contextclient.ErrCallerAuthUnproven, wantErr: false},
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

// stubContextProbe serves searchErr from a stub context server and reports the
// token metadata it observed on the probe call.
func stubContextProbe(t *testing.T, searchErr error) (string, <-chan []string) {
	t.Helper()
	observed := make(chan []string, 1)
	addr := startStubContextServer(t, &stubContextServer{
		searchErr:     searchErr,
		observedToken: observed,
	})
	return addr, observed
}

func startStubContextServer(t *testing.T, impl contextv1.ContextAssemblyServiceServer) string {
	t.Helper()
	lis := listenLoopback(t)
	srv := grpc.NewServer() // nosemgrep: go.grpc.security.grpc-server-insecure-connection -- loopback-only test stub; the caller-auth boundary is what this test exercises
	contextv1.RegisterContextAssemblyServiceServer(srv, impl)
	go func() {
		_ = srv.Serve(lis) //nolint:errcheck // Stop closes the listener; Serve then returns
	}()
	t.Cleanup(srv.Stop)
	return lis.Addr().String()
}

func closedLoopbackAddr(t *testing.T) string {
	t.Helper()
	lis := listenLoopback(t)
	addr := lis.Addr().String()
	if err := lis.Close(); err != nil {
		t.Fatalf("close listener: %v", err)
	}
	return addr
}

func listenLoopback(t *testing.T) net.Listener {
	t.Helper()
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	return lis
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
