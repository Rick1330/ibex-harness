package bootstrap

import (
	"bytes"
	"context"
	"errors"
	"fmt"
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
	"google.golang.org/grpc/credentials/insecure"
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
	srv := grpc.NewServer(grpc.Creds(insecure.NewCredentials()))
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

// TestUnit_ContextTransportCredentials pins the ADR-0097 §4 decision: a co-located
// context hop is plaintext even in production, development stays plaintext as
// before, and a non-co-located production proxy still dials TLS. SecurityProtocol
// is the observable the gRPC insecure credential reports ("insecure"); the TLS
// credential reports ("tls"). The log name must match the same decision so the
// startup line cannot claim TLS for a plaintext hop.
func TestUnit_ContextTransportCredentials(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name        string
		environment string
		colocated   bool
		wantProto   string
		wantLogged  string
	}{
		{
			name: "colocated production is plaintext", environment: "production", colocated: true,
			wantProto: "insecure", wantLogged: "plaintext-loopback-colocated",
		},
		{
			name: "development is plaintext", environment: "development", colocated: false,
			wantProto: "insecure", wantLogged: "plaintext-development",
		},
		{
			name: "production without colocation is TLS", environment: "production", colocated: false,
			wantProto: "tls", wantLogged: "tls",
		},
		{
			// An environment that was never resolved must not fall back to
			// plaintext: only development may skip TLS.
			name: "empty environment without colocation is TLS", environment: "", colocated: false,
			wantProto: "tls", wantLogged: "tls",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			cfg := config.Config{Environment: tc.environment, ContextColocated: tc.colocated}
			creds, err := contextTransportCredentials(cfg)
			if err != nil {
				t.Fatalf("contextTransportCredentials: %v", err)
			}
			if got := creds.Info().SecurityProtocol; got != tc.wantProto {
				t.Fatalf("SecurityProtocol=%q, want %q", got, tc.wantProto)
			}
			if got := contextTransportName(cfg); got != tc.wantLogged {
				t.Fatalf("contextTransportName=%q, want %q", got, tc.wantLogged)
			}
		})
	}
}

// contextReconnectBudget is the contract the fix establishes: after a failure,
// the context channel must try again within a few seconds. gRPC's default
// schedule (base 1 s, x1.6, cap 120 s) leaves the channel asleep for 96-144 s by
// the time the late context container binds, and every Assemble is fail-fast, so
// a healthy peer stays invisible for minutes.
const contextReconnectBudget = 5 * time.Second

// TestUnit_ContextConnectParams_BoundedReconnect pins the dial-time bound. It is
// the half of the fix that a behavioural test cannot state cheaply: whatever
// numbers a future change picks, the worst-case reconnect (MaxDelay plus jitter)
// must stay inside the budget the v1 smoke's warm-up retries depend on, and a
// single attempt must not inherit gRPC's 20 s MinConnectTimeout.
//
// One row per property: the loop body holds no per-property branch, so a failure
// names the property that broke and prints the value it read instead of a line
// number.
func TestUnit_ContextConnectParams_BoundedReconnect(t *testing.T) {
	t.Parallel()

	params := contextConnectParams()

	cases := []struct {
		name  string
		reads func(grpc.ConnectParams) string // renders the parameter value(s) this row pins
		want  string                          // the condition, stated for the failure message
		holds func(grpc.ConnectParams) bool
	}{
		{
			name: "base delay is positive",
			reads: func(p grpc.ConnectParams) string {
				return fmt.Sprintf("Backoff.BaseDelay=%v", p.Backoff.BaseDelay)
			},
			want:  "> 0",
			holds: func(p grpc.ConnectParams) bool { return p.Backoff.BaseDelay > 0 },
		},
		{
			name: "multiplier never shrinks the delay",
			reads: func(p grpc.ConnectParams) string {
				return fmt.Sprintf("Backoff.Multiplier=%v", p.Backoff.Multiplier)
			},
			want:  ">= 1",
			holds: func(p grpc.ConnectParams) bool { return p.Backoff.Multiplier >= 1 },
		},
		{
			name: "jitter is a fraction below one",
			reads: func(p grpc.ConnectParams) string {
				return fmt.Sprintf("Backoff.Jitter=%v", p.Backoff.Jitter)
			},
			want:  "in [0,1)",
			holds: func(p grpc.ConnectParams) bool { return p.Backoff.Jitter >= 0 && p.Backoff.Jitter < 1 },
		},
		{
			name: "base delay does not exceed the cap",
			reads: func(p grpc.ConnectParams) string {
				return fmt.Sprintf("Backoff.BaseDelay=%v, Backoff.MaxDelay=%v", p.Backoff.BaseDelay, p.Backoff.MaxDelay)
			},
			want:  "BaseDelay <= MaxDelay",
			holds: func(p grpc.ConnectParams) bool { return p.Backoff.BaseDelay <= p.Backoff.MaxDelay },
		},
		{
			// A stalled attempt must not hold the subconn the way the 20 s default
			// does.
			name: "min connect timeout is inside the reconnect budget",
			reads: func(p grpc.ConnectParams) string {
				return fmt.Sprintf("MinConnectTimeout=%v", p.MinConnectTimeout)
			},
			want: fmt.Sprintf("in (0,%v]", contextReconnectBudget),
			holds: func(p grpc.ConnectParams) bool {
				return p.MinConnectTimeout > 0 && p.MinConnectTimeout <= contextReconnectBudget
			},
		},
		{
			// The row that makes the fix work: MaxDelay is what caps the sleeping
			// channel. 2 s plus 20% jitter is 2.4 s, inside the v1 smoke's 7.5 s
			// warm-up budget, so a peer that appears mid-smoke is discovered
			// before the retries run out. gRPC's defaults (base 1 s, x1.6, cap
			// 120 s) reach 96-144 s and fail this row.
			name: "worst-case reconnect stays inside the budget",
			reads: func(p grpc.ConnectParams) string {
				worstCase := time.Duration(float64(p.Backoff.MaxDelay) * (1 + p.Backoff.Jitter))
				return fmt.Sprintf("MaxDelay=%v with Jitter=%v is a worst case of %v",
					p.Backoff.MaxDelay, p.Backoff.Jitter, worstCase)
			},
			want: fmt.Sprintf("<= %v", contextReconnectBudget),
			holds: func(p grpc.ConnectParams) bool {
				worstCase := time.Duration(float64(p.Backoff.MaxDelay) * (1 + p.Backoff.Jitter))
				return worstCase <= contextReconnectBudget
			},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if !tc.holds(params) {
				t.Fatalf("%s, want %s", tc.reads(params), tc.want)
			}
		})
	}
}

// recoveringContextServer serves AssembleContext so a successful call is
// distinguishable from the fail-open fallback the client returns on any
// transport error.
type recoveringContextServer struct {
	contextv1.UnimplementedContextAssemblyServiceServer
}

func (s *recoveringContextServer) AssembleContext(
	context.Context, *contextv1.AssembleContextRequest,
) (*contextv1.AssembleContextResponse, error) {
	return &contextv1.AssembleContextResponse{AssembledContext: "recovered", MemoriesIncluded: 1}, nil
}

// contextRecoveryParams is the smallest request Assemble accepts.
func contextRecoveryParams() contextclient.AssembleParams {
	return contextclient.AssembleParams{OrgID: "org-recovery", Model: "test-model", Query: "recovery probe"}
}

// refusingListener accepts and immediately closes connections until want of them
// have been refused, then stops accepting without consuming another one. The
// caller hands the same listener to a real gRPC server, so the next connection
// attempt is served: that is what makes "the peer appears late" deterministic
// instead of a race against a jittered schedule.
func refusingListener(t *testing.T, want int) (net.Listener, <-chan struct{}) {
	t.Helper()
	lis := listenLoopback(t)
	t.Cleanup(func() { _ = lis.Close() }) //nolint:errcheck // Stop closes it on the success path
	refused := make(chan struct{})
	go func() {
		for i := 0; i < want; i++ {
			conn, err := lis.Accept()
			if err != nil {
				return
			}
			_ = conn.Close() //nolint:errcheck // the failed handshake is the point of the test
		}
		close(refused)
	}()
	return lis, refused
}

// TestUnit_SetupContextClient_RecoversWhenPeerAppearsLate is the test that was
// missing: it starts the peer after the client has already failed several
// connection attempts, then asserts a later Assemble succeeds.
//
// The failure count matters. A single refused attempt only exercises BaseDelay,
// and the default schedule is already fast enough there — which is why the
// existing "probe UNAVAILABLE continues" test never caught this. Four failures
// put the channel past the first three backoff steps, so the next wake-up uses
// Backoff(3): 1.0 s bounded (0.8-1.2 s with jitter), 4.1 s on the default
// schedule (3.3-4.9 s), and 96-144 s once a few more failures accumulate. Four is
// the smallest count that separates the two schedules by more than the 3 s
// assertion window below.
func TestUnit_SetupContextClient_RecoversWhenPeerAppearsLate(t *testing.T) {
	// Not parallel: the assertion is a bounded reconnect delay, and the rest of
	// this package is heavy enough to make scheduler noise a needless risk.
	const refusals = 4
	lis, refused := refusingListener(t, refusals)

	// Setup dials lazily and probes once; the probe triggers the first attempted
	// connection, which is refused exactly as if the context container were late.
	got, err := setupContextClient(contextProbeConfig(lis.Addr().String()), logger.Discard("proxy"), nil)
	if err != nil {
		t.Fatalf("setupContextClient: %v", err)
	}
	requireContextClient(t, got)

	select {
	case <-refused:
	case <-time.After(30 * time.Second):
		t.Fatalf("%d connection attempts were not refused within 30s: the channel stopped retrying", refusals)
	}

	// The peer appears now, on the address the channel has been failing against.
	srv := grpc.NewServer(grpc.Creds(insecure.NewCredentials()))
	contextv1.RegisterContextAssemblyServiceServer(srv, &recoveringContextServer{})
	go func() {
		_ = srv.Serve(lis) //nolint:errcheck // Stop closes the listener; Serve then returns
	}()
	t.Cleanup(srv.Stop)
	appeared := time.Now()

	// The deadline is a literal, not a multiple of contextDialMaxDelay: deriving it
	// from the constants would widen both sides of the assertion together, so a
	// future change could leave the peer invisible for minutes and stay green.
	deadline := appeared.Add(3 * time.Second)
	for {
		res := got.client.Assemble(context.Background(), contextRecoveryParams())
		if !res.Fallback {
			t.Logf("recovered %v after the peer appeared", time.Since(appeared))
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("Assemble still fell open %v after the peer started listening (last reason %q): the channel is asleep in a backoff window instead of reconnecting",
				time.Since(appeared), res.FallbackReason)
		}
		time.Sleep(10 * time.Millisecond)
	}
}
