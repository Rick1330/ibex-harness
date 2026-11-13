package http

import (
	"bufio"
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"reflect"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/httptestx"
	"github.com/Rick1330/ibex-harness/packages/provider"
)

func mustNotice(t *testing.T, sunset string) deprecationNotice {
	t.Helper()
	sunsetAt, err := time.Parse(dateLayout, sunset)
	if err != nil {
		t.Fatalf("parse sunset %q: %v", sunset, err)
	}
	return deprecationNotice{
		deprecation: "@1798761600",
		sunset:      sunsetAt.Format(http.TimeFormat),
		sunsetAt:    sunsetAt,
	}
}

func todayUTC() time.Time {
	now := time.Now().UTC()
	return time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC)
}

func TestUnit_deprecationHeadersMiddleware(t *testing.T) {
	t.Parallel()
	today := todayUTC()
	tests := []struct {
		name    string
		notices deprecationNotices
		path    string
		want    bool
	}{
		{
			name:    "matched path announces",
			notices: deprecationNotices{"/v1/chat/completions": mustNotice(t, "2099-01-01")},
			path:    "/v1/chat/completions",
			want:    true,
		},
		{
			name:    "unmatched path is silent",
			notices: deprecationNotices{"/v1/chat/completions": mustNotice(t, "2099-01-01")},
			path:    "/v1/responses",
			want:    false,
		},
		{
			name:    "empty record is silent",
			notices: nil,
			path:    "/v1/chat/completions",
			want:    false,
		},
		{
			name:    "sunset day still announces",
			notices: deprecationNotices{"/v1/chat/completions": mustNotice(t, today.Format(dateLayout))},
			path:    "/v1/chat/completions",
			want:    true,
		},
		{
			name:    "day after sunset is silent",
			notices: deprecationNotices{"/v1/chat/completions": mustNotice(t, today.AddDate(0, 0, -1).Format(dateLayout))},
			path:    "/v1/chat/completions",
			want:    false,
		},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			rec := serveDeprecationProbe(t, tc.notices, tc.path)
			if !tc.want {
				requireNoDeprecationHeaders(t, rec)
				return
			}
			t.Logf("%s %s -> Deprecation=%q Sunset=%q", http.MethodPost, tc.path,
				rec.Header().Get(headerDeprecation), rec.Header().Get(headerSunset))
			requireDeprecationHeaders(t, rec, tc.notices[tc.path])
		})
	}
}

// serveDeprecationProbe runs one request through the emitter and returns the
// recorded response, failing if the wrapped handler never ran.
func serveDeprecationProbe(t *testing.T, notices deprecationNotices, path string) *httptest.ResponseRecorder {
	t.Helper()
	ran := false
	handler := deprecationHeadersMiddleware(notices)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		ran = true
		w.WriteHeader(http.StatusOK)
	}))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodPost, path, nil))
	if !ran {
		t.Fatal("wrapped handler did not run")
	}
	return rec
}

// requireNoDeprecationHeaders pins that an unmatched path or an empty record
// emits neither header.
func requireNoDeprecationHeaders(t *testing.T, rec *httptest.ResponseRecorder) {
	t.Helper()
	deprecation := rec.Header().Get(headerDeprecation)
	sunset := rec.Header().Get(headerSunset)
	if deprecation != "" || sunset != "" {
		t.Fatalf("expected no headers, got Deprecation=%q Sunset=%q", deprecation, sunset)
	}
}

// requireDeprecationHeaders pins both header values to the recorded notice.
func requireDeprecationHeaders(t *testing.T, rec *httptest.ResponseRecorder, notice deprecationNotice) {
	t.Helper()
	deprecation := rec.Header().Get(headerDeprecation)
	sunset := rec.Header().Get(headerSunset)
	if deprecation != notice.deprecation {
		t.Fatalf("Deprecation: got %q want %q", deprecation, notice.deprecation)
	}
	if sunset != notice.sunset {
		t.Fatalf("Sunset: got %q want %q", sunset, notice.sunset)
	}
}

// TestUnit_deprecationHeadersMiddleware_passesWriterThrough pins the property
// that makes the emitter safe for SSE: it must hand the handler the exact
// ResponseWriter it received, because forwardSSEStream type-asserts
// http.Flusher and http.NewResponseController needs the unwrapped writer.
func TestUnit_deprecationHeadersMiddleware_passesWriterThrough(t *testing.T) {
	t.Parallel()
	notices := deprecationNotices{"/v1/chat/completions": mustNotice(t, "2099-01-01")}
	var got http.ResponseWriter
	handler := deprecationHeadersMiddleware(notices)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		got = w
	}))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil))
	if got != http.ResponseWriter(rec) {
		t.Fatalf("handler received a wrapped writer %T, want the original %T", got, rec)
	}
}

func TestUnit_deprecationHeadersMiddleware_emptyRecordReturnsNextUnchanged(t *testing.T) {
	t.Parallel()
	next := http.HandlerFunc(func(http.ResponseWriter, *http.Request) {})
	if got := deprecationHeadersMiddleware(nil)(next); reflect.ValueOf(got).Pointer() != reflect.ValueOf(next).Pointer() {
		t.Fatalf("empty record wrapped the handler: %T", got)
	}
}

func TestUnit_NewRouter_deprecationHeadersFollowTheMuxSurface(t *testing.T) {
	t.Parallel()
	record := writeDeprecationRecord(t, strings.Join([]string{
		announcedProxyEntry("d1", "/health"),
		announcedProxyEntry("d2", "/v1/chat/completions"),
	}, ","))
	deps := defaultChatRouterDeps(t)
	deps.Config.DeprecationsFile = record
	router := mustNewRouter(t, deps)

	requireAnnouncedRoute(t, router, routeProbe{method: http.MethodGet, path: "/health", wantStatus: http.StatusOK})
	requireSilentRoute(t, router, routeProbe{method: http.MethodGet, path: "/ready"})
	requireProtectedChatAnnounces(t, router)
}

// routeProbe is one request against the router under test, with the status the
// response must carry.
type routeProbe struct {
	method     string
	path       string
	wantStatus int
}

// requireAnnouncedRoute serves one request and requires the deprecation headers
// on its response.
func requireAnnouncedRoute(t *testing.T, router http.Handler, probe routeProbe) {
	t.Helper()
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequest(probe.method, probe.path, nil))
	if rec.Code != probe.wantStatus {
		t.Fatalf("%s %s status: %d, want %d", probe.method, probe.path, rec.Code, probe.wantStatus)
	}
	if rec.Header().Get(headerDeprecation) == "" || rec.Header().Get(headerSunset) == "" {
		t.Fatalf("%s %s: matched route missing headers: %v", probe.method, probe.path, rec.Header())
	}
	t.Logf("%s %s -> %d Deprecation=%q Sunset=%q", probe.method, probe.path, rec.Code,
		rec.Header().Get(headerDeprecation), rec.Header().Get(headerSunset))
}

// requireSilentRoute serves one request and requires no deprecation headers. It
// asserts nothing about the status: the point is that the route is not named by
// the record.
func requireSilentRoute(t *testing.T, router http.Handler, probe routeProbe) {
	t.Helper()
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequest(probe.method, probe.path, nil))
	if rec.Header().Get(headerDeprecation) != "" || rec.Header().Get(headerSunset) != "" {
		t.Fatalf("%s %s: unmatched route got headers: %v", probe.method, probe.path, rec.Header())
	}
	t.Logf("%s %s -> %d Deprecation=%q Sunset=%q (none)", probe.method, probe.path, rec.Code,
		rec.Header().Get(headerDeprecation), rec.Header().Get(headerSunset))
}

// requireProtectedChatAnnounces pins that the notice rides on the protected chat
// route too, including an auth rejection.
func requireProtectedChatAnnounces(t *testing.T, router http.Handler) {
	t.Helper()
	chat := postChat(t, router, chatRequestOpts{
		body: `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
	})
	if chat.Code != http.StatusUnauthorized {
		t.Fatalf("chat status: %d, want 401 (route mounted behind auth)", chat.Code)
	}
	if chat.Header().Get(headerDeprecation) == "" || chat.Header().Get(headerSunset) == "" {
		t.Fatalf("protected route missing headers: status=%d headers=%v", chat.Code, chat.Header())
	}
}

// TestUnit_NewRouter_readsTheRecordOnce proves the emitter does no per-request
// file I/O: the record is emptied on disk after startup and the headers still
// come from the loaded snapshot.
func TestUnit_NewRouter_readsTheRecordOnce(t *testing.T) {
	t.Parallel()
	record := writeDeprecationRecord(t, announcedProxyEntry("d1", "/health"))
	deps := defaultChatRouterDeps(t)
	deps.Config.DeprecationsFile = record
	router := mustNewRouter(t, deps)

	if err := os.WriteFile(record, []byte(`{"schema":"ibex.deprecations.v1","entries":[]}`), 0o600); err != nil {
		t.Fatalf("rewrite record: %v", err)
	}

	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/health", nil))
	if rec.Header().Get(headerDeprecation) == "" || rec.Header().Get(headerSunset) == "" {
		t.Fatalf("headers vanished after the file changed: the record was re-read per request")
	}
}

func TestUnit_NewRouter_emptyRecordAddsNoHeader(t *testing.T) {
	t.Parallel()
	deps := defaultChatRouterDeps(t)
	deps.Config.DeprecationsFile = writeDeprecationRecord(t, "")
	router := mustNewRouter(t, deps)

	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/health", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("health status: %d", rec.Code)
	}
	if rec.Header().Get(headerDeprecation) != "" || rec.Header().Get(headerSunset) != "" {
		t.Fatalf("empty record emitted headers: %v", rec.Header())
	}
}

func TestUnit_NewRouter_malformedRecordFailsStartup(t *testing.T) {
	t.Parallel()
	deps := defaultChatRouterDeps(t)
	deps.Config.DeprecationsFile = writeDeprecationRecord(t, `{"id":"d1","surface":"proxy"}`)
	handler, err := NewRouter(deps)
	if err == nil {
		t.Fatalf("expected startup error, got handler %T", handler)
	}
	if handler != nil {
		t.Fatal("a router that failed startup must not be served")
	}
}

const testSSEFirstEvent = `data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1,` +
	`"model":"gpt-4o","choices":[{"index":0,"delta":{"content":"a"},"finish_reason":null}]}` + "\n\n"

// gatedSSEProvider streams one event, then blocks until the test releases it
// before sending [DONE]. The pipe write blocks on the reader, so the first
// event only reaches the client if the proxy flushed it while the handler was
// still running.
type gatedSSEProvider struct {
	release <-chan struct{}
}

func (p *gatedSSEProvider) Name() string { return "openai" }

func (p *gatedSSEProvider) SupportedModels() []string { return []string{"gpt-4o"} }

func (p *gatedSSEProvider) Complete(ctx context.Context, _ provider.Request) (provider.Response, error) {
	pr, pw := io.Pipe()
	go func() {
		if _, err := pw.Write([]byte(testSSEFirstEvent)); err != nil {
			_ = pw.CloseWithError(err)
			return
		}
		select {
		case <-p.release:
		case <-ctx.Done():
			_ = pw.CloseWithError(ctx.Err())
			return
		}
		_, _ = pw.Write([]byte("data: [DONE]\n\n"))
		_ = pw.Close()
	}()
	return provider.Response{StatusCode: http.StatusOK, Body: pr}, nil
}

type streamProbe struct {
	resp   *http.Response
	reader *bufio.Reader
	line   string
	err    error
}

// gatedStream is one in-flight streaming chat request: the response headers,
// the first SSE line that reached the client, and the reader for the rest.
type gatedStream struct {
	headers http.Header
	reader  *bufio.Reader
	first   string
	release func()
}

// TestUnit_deprecationHeaders_streamingStillStreams drives the real chat
// handler through httptest.Server with a deprecation announced on the path: the
// headers ride on the response and the first SSE event arrives while the
// provider is still blocked, so flushing survived the wrapper.
func TestUnit_deprecationHeaders_streamingStillStreams(t *testing.T) {
	t.Parallel()
	stream := openGatedStream(t)

	if stream.headers.Get(headerDeprecation) == "" {
		t.Fatalf("streaming response missing Deprecation: %v", stream.headers)
	}
	if stream.headers.Get(headerSunset) == "" {
		t.Fatalf("streaming response missing Sunset: %v", stream.headers)
	}
	if !strings.Contains(stream.first, `"content":"a"`) {
		t.Fatalf("first chunk: %q", stream.first)
	}
	t.Logf("stream headers: Deprecation=%q Sunset=%q Content-Type=%q",
		stream.headers.Get(headerDeprecation), stream.headers.Get(headerSunset),
		stream.headers.Get("Content-Type"))
	t.Logf("first chunk arrived while the provider was still blocked: %q", stream.first)

	// The provider is still blocked, so the rest of the stream only completes
	// after the release: the connection is live, not buffered to the end.
	stream.release()
	rest := readAllWithin(t, stream.reader, 5*time.Second)
	if !strings.Contains(rest, "data: [DONE]") {
		t.Fatalf("stream did not finish: %q", rest)
	}
	t.Logf("after release: %q", rest)
}

// openGatedStream starts one streaming chat request against the real router
// with a deprecation announced on the path, and returns once the first SSE event
// has reached the client while the provider is still blocked.
func openGatedStream(t *testing.T) gatedStream {
	t.Helper()
	release := make(chan struct{})
	var releaseOnce sync.Once
	releaseStream := func() { releaseOnce.Do(func() { close(release) }) }

	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), &gatedSSEProvider{release: release})
	if err != nil {
		t.Fatalf("registry: %v", err)
	}
	deps := defaultChatRouterDeps(t)
	deps.Config.DeprecationsFile = writeDeprecationRecord(t, announcedProxyEntry("d1", "/v1/chat/completions"))
	deps.ProviderRegistry = reg
	server := httptest.NewServer(mustNewRouter(t, deps))
	// One cleanup, in this order: the handler is blocked on the provider until
	// the release, and Close waits for it, so a failed assertion must release
	// first or the test binary deadlocks instead of reporting.
	t.Cleanup(func() {
		releaseStream()
		server.Close()
	})

	req, err := http.NewRequest(http.MethodPost, server.URL+"/v1/chat/completions", strings.NewReader(
		`{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}],"stream":true}`))
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	httptestx.ApplyChatHeaders(req, httptestx.ChatHeaders{
		Auth: true, ContentType: "application/json", AgentID: testChatAgentID, HasBody: true,
	})

	probe := awaitFirstChunk(t, server.Client(), req)
	t.Cleanup(func() { _ = probe.resp.Body.Close() })
	return gatedStream{
		headers: probe.resp.Header,
		reader:  probe.reader,
		first:   probe.line,
		release: releaseStream,
	}
}

// awaitFirstChunk reads the first SSE line of a streaming request, failing if
// the response headers or the first event did not flush within 5s.
func awaitFirstChunk(t *testing.T, client *http.Client, req *http.Request) streamProbe {
	t.Helper()
	probes := make(chan streamProbe, 1)
	go func() {
		resp, doErr := client.Do(req)
		if doErr != nil {
			probes <- streamProbe{err: doErr}
			return
		}
		reader := bufio.NewReader(resp.Body)
		line, readErr := reader.ReadString('\n')
		probes <- streamProbe{resp: resp, reader: reader, line: line, err: readErr}
	}()

	select {
	case probe := <-probes:
		if probe.err != nil {
			t.Fatalf("stream probe: %v", probe.err)
		}
		if probe.resp.StatusCode != http.StatusOK {
			t.Fatalf("status: %d", probe.resp.StatusCode)
		}
		return probe
	case <-time.After(5 * time.Second):
		t.Fatal("no streamed chunk within 5s: the response headers or the first event did not flush")
		return streamProbe{}
	}
}

func readAllWithin(t *testing.T, reader io.Reader, timeout time.Duration) string {
	t.Helper()
	type result struct {
		body string
		err  error
	}
	done := make(chan result, 1)
	go func() {
		body, err := io.ReadAll(reader)
		done <- result{body: string(body), err: err}
	}()
	select {
	case got := <-done:
		if got.err != nil {
			t.Fatalf("read rest of stream: %v", got.err)
		}
		return got.body
	case <-time.After(timeout):
		t.Fatal("stream did not finish after the provider was released")
		return ""
	}
}

// discardResponseWriter lets the benchmark measure the middleware alone.
type discardResponseWriter struct{ header http.Header }

func (d *discardResponseWriter) Header() http.Header { return d.header }

func (d *discardResponseWriter) Write(p []byte) (int, error) { return len(p), nil }

func (d *discardResponseWriter) WriteHeader(int) {}

// BenchmarkDeprecationHeaders measures the per-request cost of the emitter.
// The shipped record is empty, so the middleware returns the mux unchanged and
// the request path pays nothing; an unmatched path costs one map lookup and
// allocates nothing.
func BenchmarkDeprecationHeaders(b *testing.B) {
	notice := deprecationNotice{
		deprecation: "@1798761600",
		sunset:      time.Date(2027, 6, 30, 0, 0, 0, 0, time.UTC).Format(http.TimeFormat),
		sunsetAt:    time.Date(2027, 6, 30, 0, 0, 0, 0, time.UTC),
	}
	cases := []struct {
		name    string
		notices deprecationNotices
		path    string
	}{
		{name: "empty record", notices: nil, path: "/v1/chat/completions"},
		{name: "unmatched path", notices: deprecationNotices{"/v1/chat/completions": notice}, path: "/health"},
		{name: "matched path", notices: deprecationNotices{"/v1/chat/completions": notice}, path: "/v1/chat/completions"},
	}
	for _, tc := range cases {
		tc := tc
		b.Run(tc.name, func(b *testing.B) {
			handler := deprecationHeadersMiddleware(tc.notices)(
				http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
			req := httptest.NewRequest(http.MethodPost, tc.path, nil)
			w := &discardResponseWriter{header: http.Header{}}
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				handler.ServeHTTP(w, req)
			}
		})
	}
}
