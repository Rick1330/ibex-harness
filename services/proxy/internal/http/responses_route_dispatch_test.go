package http

import (
	"bytes"
	"context"
	"errors"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/responses"
	"github.com/Rick1330/ibex-harness/packages/ssrf"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/credentials"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

type fakeResponsesUsageInserter struct {
	rows [][]billing.UsageFact
	err  error
}

func (f *fakeResponsesUsageInserter) InsertUsageFacts(_ context.Context, rows []billing.UsageFact) error {
	cp := make([]billing.UsageFact, len(rows))
	copy(cp, rows)
	f.rows = append(f.rows, cp)
	return f.err
}
func (f *fakeResponsesUsageInserter) Close() error { return nil }

type scriptedResponsesProvider struct {
	calls int
	resp  responses.Response
	err   error
}

func (p *scriptedResponsesProvider) Complete(context.Context, provider.Request) (provider.Response, error) {
	return provider.Response{}, nil
}
func (p *scriptedResponsesProvider) Name() string              { return "openai" }
func (p *scriptedResponsesProvider) SupportedModels() []string { return []string{"gpt-4o"} }
func (p *scriptedResponsesProvider) CreateResponse(context.Context, responses.Request, responses.CredentialOverride) (responses.Response, error) {
	p.calls++
	return p.resp, p.err
}

func fullUsageResponse() responses.Response {
	out, _ := responses.ParseResponse([]byte(`{"id":"r","status":"completed","usage":{"input_tokens":2,"output_tokens":3,"total_tokens":5},"output":[]}`))
	return out
}

func discardLogger() *logger.Logger { return logger.Discard("proxy") }

func bufferedWarnLogger(t *testing.T) (*logger.Logger, *bytes.Buffer) {
	t.Helper()
	buf := &bytes.Buffer{}
	log, err := logger.New(logger.Config{Service: "proxy", Level: slog.LevelWarn, Writer: buf})
	if err != nil {
		t.Fatalf("logger: %v", err)
	}
	return log, buf
}

func newResponsesWriter(t *testing.T, bufSize int) (*billing.UsageFactWriter, *fakeResponsesUsageInserter) {
	t.Helper()
	ins := &fakeResponsesUsageInserter{}
	w := billing.NewUsageFactWriterWithInserter(ins, billing.UsageFactConfig{
		MaxBatchSize:  1000,
		MaxBufferSize: bufSize,
		FlushInterval: time.Hour,
	})
	t.Cleanup(func() { _ = w.Shutdown(context.Background()) })
	return w, ins
}

var responsesTestOrgID = uuid.MustParse("22222222-2222-2222-2222-222222222222")
var responsesTestAgentID = uuid.MustParse("33333333-3333-3333-3333-333333333333")

func responsesRequestContext(t *testing.T, req responses.Request, prov provider.Provider, org, agent uuid.UUID, requestID string) context.Context {
	t.Helper()
	ctx := llm.WithResponsesRequest(context.Background(), req)
	if prov != nil {
		ctx = provider.WithProvider(ctx, prov)
	}
	if org != uuid.Nil {
		ctx = auth.WithContext(ctx, &auth.ValidateResult{OrgID: org, AgentID: agent})
	}
	if agent != uuid.Nil {
		ctx = WithAgent(ctx, auth.AgentRecord{ID: agent, OrgID: org})
	}
	if requestID != "" {
		ctx = WithRequestID(ctx, requestID)
	}
	return ctx
}

func responsesDispatchRequest(t *testing.T, ctx context.Context, authHeader string) *http.Request {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/v1/responses", nil)
	if authHeader != "" {
		req.Header.Set("Authorization", authHeader)
	}
	return req.WithContext(ctx)
}

func TestResponsesHandleHappyPathWritesUsage(t *testing.T) {
	writer, ins := newResponsesWriter(t, 100)
	prov := &scriptedResponsesProvider{resp: fullUsageResponse()}
	deps := responsesDeps(writer, credentials.Result{PlatformDefault: true}, discardLogger())
	ctx := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, prov, responsesTestOrgID, responsesTestAgentID, "req-happy")
	rr := httptest.NewRecorder()
	handleResponses(rr, responsesDispatchRequest(t, ctx, "Bearer ibex_pat_x"), deps)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	if prov.calls != 1 {
		t.Fatalf("provider calls=%d", prov.calls)
	}
	if got := rr.Header().Get("X-IBEX-Usage-Accounting"); got != "" {
		t.Fatalf("unexpected pending header: %q", got)
	}
	if err := writer.Flush(context.Background()); err != nil {
		t.Fatal(err)
	}
	assertUsageFact(t, singleUsageFact(t, ins), "req-happy", "openai", "gpt-4o")
}

func responsesDeps(writer *billing.UsageFactWriter, result credentials.Result, log *logger.Logger) protectedRouteDeps {
	return protectedRouteDeps{credentialResolver: &stubCredentialResolver{result: result}, usageFactWriter: writer, logger: log}
}

func singleUsageFact(t *testing.T, ins *fakeResponsesUsageInserter) billing.UsageFact {
	t.Helper()
	if len(ins.rows) != 1 {
		t.Fatalf("usage batches=%d", len(ins.rows))
	}
	if len(ins.rows[0]) != 1 {
		t.Fatalf("usage rows=%d", len(ins.rows[0]))
	}
	return ins.rows[0][0]
}

func assertUsageFact(t *testing.T, fact billing.UsageFact, requestID, providerName, model string) {
	t.Helper()
	if fact.RequestID != requestID {
		t.Fatalf("request_id=%q", fact.RequestID)
	}
	if fact.Provider != providerName {
		t.Fatalf("provider=%q", fact.Provider)
	}
	if fact.Model != model {
		t.Fatalf("model=%q", fact.Model)
	}
}

func TestResponsesHandleUsesTenantPinnedCredential(t *testing.T) {
	restore := ssrf.SetLookupIPAddrForTest(func(_ context.Context, host string) ([]net.IPAddr, error) {
		return []net.IPAddr{{IP: net.ParseIP("1.1.1.1")}}, nil
	})
	t.Cleanup(restore)
	resolver := &stubCredentialResolver{result: credentials.Result{APIKey: "sk-byo", BaseURL: "https://byo.example.test/v1"}}
	deps := protectedRouteDeps{credentialResolver: resolver, usageFactWriter: mustWriter(t), logger: discardLogger()}
	ctx := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, &scriptedResponsesProvider{resp: fullUsageResponse()}, responsesTestOrgID, responsesTestAgentID, "req-byo")
	rr := httptest.NewRecorder()
	handleResponses(rr, responsesDispatchRequest(t, ctx, "Bearer ibex_pat_x"), deps)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	if resolver.last.ProviderName != "openai" || resolver.last.OrgID != responsesTestOrgID.String() {
		t.Fatalf("resolve input=%+v", resolver.last)
	}
}

func TestResponsesHandleRejectsMalformedJourney(t *testing.T) {
	writer := mustWriter(t)
	cases := []struct {
		name        string
		deps        protectedRouteDeps
		ctx         context.Context
		authHeader  string
		wantStatus  int
		wantCallNil bool
	}{
		{
			name:       "missing request",
			deps:       responsesDeps(writer, credentials.Result{}, discardLogger()),
			ctx:        provider.WithProvider(context.Background(), &scriptedResponsesProvider{}),
			authHeader: "Bearer ibex_pat_x",
			wantStatus: http.StatusInternalServerError,
		},
		{
			name:       "missing provider",
			deps:       responsesDeps(writer, credentials.Result{}, discardLogger()),
			ctx:        llm.WithResponsesRequest(context.Background(), responses.Request{Model: "gpt-4o"}),
			authHeader: "Bearer ibex_pat_x",
			wantStatus: http.StatusInternalServerError,
		},
		{
			name:       "provider lacks responses surface",
			deps:       responsesDeps(writer, credentials.Result{}, discardLogger()),
			ctx:        responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, &responsesNonProvider{}, responsesTestOrgID, responsesTestAgentID, "req-1"),
			authHeader: "Bearer ibex_pat_x",
			wantStatus: http.StatusUnprocessableEntity,
		},
		{
			name:       "nil dependencies",
			deps:       protectedRouteDeps{},
			ctx:        responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, &scriptedResponsesProvider{}, responsesTestOrgID, responsesTestAgentID, "req-1"),
			authHeader: "Bearer ibex_pat_x",
			wantStatus: http.StatusServiceUnavailable,
		},
		{
			name:       "missing org",
			deps:       responsesDeps(writer, credentials.Result{}, discardLogger()),
			ctx:        responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, &scriptedResponsesProvider{}, uuid.Nil, uuid.Nil, "req-1"),
			authHeader: "Bearer ibex_pat_x",
			wantStatus: http.StatusServiceUnavailable,
		},
		{
			name:       "invalid auth header",
			deps:       responsesDeps(writer, credentials.Result{}, discardLogger()),
			ctx:        responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, &scriptedResponsesProvider{}, responsesTestOrgID, responsesTestAgentID, "req-1"),
			authHeader: "",
			wantStatus: http.StatusUnauthorized,
		},
		{
			name:       "resolver failure",
			deps:       protectedRouteDeps{credentialResolver: &stubCredentialResolver{err: errors.New("auth down")}, usageFactWriter: writer, logger: discardLogger()},
			ctx:        responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, &scriptedResponsesProvider{}, responsesTestOrgID, responsesTestAgentID, "req-1"),
			authHeader: "Bearer ibex_pat_x",
			wantStatus: http.StatusServiceUnavailable,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rr := httptest.NewRecorder()
			handleResponses(rr, responsesDispatchRequest(t, tc.ctx, tc.authHeader), tc.deps)
			if rr.Code != tc.wantStatus {
				t.Fatalf("status=%d want=%d body=%s", rr.Code, tc.wantStatus, rr.Body.String())
			}
		})
	}
}

type responsesNonProvider struct{}

func (responsesNonProvider) Complete(context.Context, provider.Request) (provider.Response, error) {
	return provider.Response{}, nil
}
func (responsesNonProvider) Name() string              { return "openai" }
func (responsesNonProvider) SupportedModels() []string { return []string{"gpt-4o"} }

func TestResponsesHandleCredentialSSRFFailure(t *testing.T) {
	deps := protectedRouteDeps{
		credentialResolver: &stubCredentialResolver{result: credentials.Result{APIKey: "sk", BaseURL: "https://127.0.0.1/v1"}},
		usageFactWriter:    mustWriter(t), logger: discardLogger(),
	}
	ctx := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, &scriptedResponsesProvider{}, responsesTestOrgID, responsesTestAgentID, "req-ssrf")
	rr := httptest.NewRecorder()
	handleResponses(rr, responsesDispatchRequest(t, ctx, "Bearer ibex_pat_x"), deps)
	if rr.Code != http.StatusUnprocessableEntity {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}

func TestResponsesHandleProviderFailure(t *testing.T) {
	deps := protectedRouteDeps{
		credentialResolver: &stubCredentialResolver{result: credentials.Result{PlatformDefault: true}},
		usageFactWriter:    mustWriter(t), logger: discardLogger(),
	}
	prov := &scriptedResponsesProvider{err: errors.New("upstream boom")}
	ctx := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, prov, responsesTestOrgID, responsesTestAgentID, "req-fail")
	rr := httptest.NewRecorder()
	handleResponses(rr, responsesDispatchRequest(t, ctx, "Bearer ibex_pat_x"), deps)
	if rr.Code != http.StatusBadGateway {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}

func TestResponsesHandleAccountingPendingPathsLogWithRequestID(t *testing.T) {
	cases := []struct {
		name       string
		usage      *responses.Usage
		requestID  string
		org, agent uuid.UUID
		wantReason string
	}{
		{name: "missing usage", usage: nil, requestID: "req-usage", org: responsesTestOrgID, agent: responsesTestAgentID, wantReason: "did not include usage"},
		{name: "usage overflow", usage: &responses.Usage{InputTokens: int(^uint32(0)) + 1, OutputTokens: 1, TotalTokens: 1}, requestID: "req-overflow", org: responsesTestOrgID, agent: responsesTestAgentID, wantReason: "exceeds billing limits"},
		{name: "missing request id", usage: &responses.Usage{InputTokens: 1, OutputTokens: 1, TotalTokens: 2}, requestID: "", org: responsesTestOrgID, agent: responsesTestAgentID, wantReason: "request identity missing"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			log, buf := bufferedWarnLogger(t)
			writer, _ := newResponsesWriter(t, 100)
			deps := protectedRouteDeps{credentialResolver: &stubCredentialResolver{result: credentials.Result{PlatformDefault: true}}, usageFactWriter: writer, logger: log}
			prov := &scriptedResponsesProvider{resp: responses.Response{Usage: tc.usage, Raw: []byte(`{}`)}}
			ctx := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, prov, tc.org, tc.agent, tc.requestID)
			rr := httptest.NewRecorder()
			handleResponses(rr, responsesDispatchRequest(t, ctx, "Bearer ibex_pat_x"), deps)
			if rr.Code != http.StatusOK {
				t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
			}
			if rr.Header().Get("X-IBEX-Usage-Accounting") != "pending" {
				t.Fatalf("pending header=%q", rr.Header().Get("X-IBEX-Usage-Accounting"))
			}
			logged := buf.String()
			if !strings.Contains(logged, "responses usage accounting pending") || !strings.Contains(logged, tc.wantReason) {
				t.Fatalf("log=%s", logged)
			}
			if tc.requestID != "" && !strings.Contains(logged, tc.requestID) {
				t.Fatalf("request id missing from log: %s", logged)
			}
		})
	}
}

func TestResponsesHandleAccountingBufferFullLogs(t *testing.T) {
	log, buf := bufferedWarnLogger(t)
	writer, _ := newResponsesWriter(t, 1)
	if err := writer.Write(billing.UsageFact{RequestID: "filler", OrgID: responsesTestOrgID, AgentID: responsesTestAgentID, Provider: "openai", Model: "gpt-4o", RateCardVersion: "responses-v1", Completeness: "complete", OccurredAt: time.Now().UTC()}); err != nil {
		t.Fatal(err)
	}
	deps := protectedRouteDeps{credentialResolver: &stubCredentialResolver{result: credentials.Result{PlatformDefault: true}}, usageFactWriter: writer, logger: log}
	ctx := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, &scriptedResponsesProvider{resp: fullUsageResponse()}, responsesTestOrgID, responsesTestAgentID, "req-buffer")
	rr := httptest.NewRecorder()
	handleResponses(rr, responsesDispatchRequest(t, ctx, "Bearer ibex_pat_x"), deps)
	if rr.Header().Get("X-IBEX-Usage-Accounting") != "pending" {
		t.Fatalf("pending header=%q", rr.Header().Get("X-IBEX-Usage-Accounting"))
	}
	if !strings.Contains(buf.String(), "buffer full") {
		t.Fatalf("log=%s", buf.String())
	}
}

func TestRecordResponsesUsageMissingTenantLogsPending(t *testing.T) {
	log, buf := bufferedWarnLogger(t)
	writer := mustWriter(t)
	ctx := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, &scriptedResponsesProvider{}, uuid.Nil, uuid.Nil, "req-tenant")
	req := responsesDispatchRequest(t, ctx, "Bearer ibex_pat_x")
	rr := httptest.NewRecorder()
	recordResponsesUsage(rr, req, protectedRouteDeps{usageFactWriter: writer, logger: log}, responsesUsageInput{Provider: "openai", Model: "gpt-4o", Usage: &responses.Usage{InputTokens: 1, OutputTokens: 1, TotalTokens: 2}})
	if rr.Header().Get("X-IBEX-Usage-Accounting") != "pending" {
		t.Fatalf("pending header=%q", rr.Header().Get("X-IBEX-Usage-Accounting"))
	}
	if !strings.Contains(buf.String(), "tenant identity missing") || !strings.Contains(buf.String(), "req-tenant") {
		t.Fatalf("log=%s", buf.String())
	}
}

func TestResolveResponsesCredentialPlatformDefaultOmitsEndpoint(t *testing.T) {
	resolver := &stubCredentialResolver{result: credentials.Result{APIKey: "platform-key", PlatformDefault: true}}
	ctx := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, nil, responsesTestOrgID, responsesTestAgentID, "req")
	rr := httptest.NewRecorder()
	cred, ok := resolveResponsesCredential(rr, responsesDispatchRequest(t, ctx, "Bearer ibex_pat_x"), resolver, "openai")
	if !ok || cred.APIKey != "platform-key" || cred.BaseURL != "" || cred.TLSServerName != "" {
		t.Fatalf("cred=%+v ok=%v", cred, ok)
	}
}

func TestResolveResponsesCredentialEmptyBaseURLUsesPlatformKey(t *testing.T) {
	resolver := &stubCredentialResolver{result: credentials.Result{APIKey: "k"}}
	ctx := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, nil, responsesTestOrgID, responsesTestAgentID, "req")
	rr := httptest.NewRecorder()
	cred, ok := resolveResponsesCredential(rr, responsesDispatchRequest(t, ctx, "Bearer ibex_pat_x"), resolver, "openai")
	if !ok || cred.APIKey != "k" || cred.BaseURL != "" {
		t.Fatalf("cred=%+v ok=%v", cred, ok)
	}
}

func TestResolveResponsesCredentialPinned(t *testing.T) {
	restore := ssrf.SetLookupIPAddrForTest(func(context.Context, string) ([]net.IPAddr, error) {
		return []net.IPAddr{{IP: net.ParseIP("1.1.1.1")}}, nil
	})
	t.Cleanup(restore)
	resolver := &stubCredentialResolver{result: credentials.Result{APIKey: "sk", BaseURL: "https://byo.example.test/v1"}}
	ctx := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, nil, responsesTestOrgID, responsesTestAgentID, "req")
	rr := httptest.NewRecorder()
	cred, ok := resolveResponsesCredential(rr, responsesDispatchRequest(t, ctx, "Bearer ibex_pat_x"), resolver, "openai")
	if !ok || !strings.Contains(cred.BaseURL, "1.1.1.1") || cred.TLSServerName != "byo.example.test" {
		t.Fatalf("cred=%+v ok=%v", cred, ok)
	}
}

func validResponsesUsage() responsesUsageInput {
	return responsesUsageInput{Provider: "openai", Model: "gpt-4o", Usage: &responses.Usage{InputTokens: 2, OutputTokens: 3, TotalTokens: 5}}
}

func TestEnqueueResponsesUsageWritesFact(t *testing.T) {
	writer, ins := newResponsesWriter(t, 100)
	ctx := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, nil, responsesTestOrgID, responsesTestAgentID, "req-enqueue")
	if err := enqueueResponsesUsage(ctx, writer, validResponsesUsage()); err != nil {
		t.Fatal(err)
	}
	if err := writer.Flush(context.Background()); err != nil {
		t.Fatal(err)
	}
	assertUsageFact(t, singleUsageFact(t, ins), "req-enqueue", "openai", "gpt-4o")
}

func TestEnqueueResponsesUsageRejectsInvalidUsage(t *testing.T) {
	writer, _ := newResponsesWriter(t, 100)
	ctx := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, nil, responsesTestOrgID, responsesTestAgentID, "req-enqueue")
	overflow := int(^uint32(0)) + 1
	for _, bad := range []responsesUsageInput{
		{Provider: "openai", Model: "gpt-4o", Usage: nil},
		{Provider: "openai", Model: "gpt-4o", Usage: &responses.Usage{InputTokens: overflow}},
		{Provider: "openai", Model: "gpt-4o", Usage: &responses.Usage{OutputTokens: overflow}},
	} {
		if err := enqueueResponsesUsage(ctx, writer, bad); err == nil {
			t.Fatalf("expected error for %+v", bad.Usage)
		}
	}
}

func TestEnqueueResponsesUsageRequiresTenantAndRequestID(t *testing.T) {
	writer, _ := newResponsesWriter(t, 100)
	noTenant := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, nil, uuid.Nil, uuid.Nil, "req")
	if err := enqueueResponsesUsage(noTenant, writer, validResponsesUsage()); err == nil {
		t.Fatal("expected tenant identity error")
	}
	noRequestID := responsesRequestContext(t, responses.Request{Model: "gpt-4o"}, nil, responsesTestOrgID, responsesTestAgentID, "")
	if err := enqueueResponsesUsage(noRequestID, writer, validResponsesUsage()); err == nil {
		t.Fatal("expected request identity error")
	}
}

func TestValidateResponsesUsage(t *testing.T) {
	if err := validateResponsesUsage(nil); err == nil {
		t.Fatal("nil usage must fail")
	}
	if err := validateResponsesUsage(&responses.Usage{InputTokens: int(^uint32(0)) + 1}); err == nil {
		t.Fatal("overflow input must fail")
	}
	if err := validateResponsesUsage(&responses.Usage{OutputTokens: int(^uint32(0)) + 1}); err == nil {
		t.Fatal("overflow output must fail")
	}
	if err := validateResponsesUsage(&responses.Usage{InputTokens: 1, OutputTokens: 1, TotalTokens: 2}); err != nil {
		t.Fatalf("valid usage rejected: %v", err)
	}
}

func TestResponsesCapabilityMiddlewareFallsBackToChatModel(t *testing.T) {
	prov := &responsesTestProvider{}
	req := httptest.NewRequest(http.MethodPost, "/v1/responses", nil)
	ctx := llm.WithResponsesRequest(req.Context(), responses.Request{})
	ctx = llm.WithChatRequest(ctx, &llm.ChatCompletionRequest{Model: "gpt-4o"})
	ctx = provider.WithProvider(ctx, prov)
	rr := runResponsesGate(t, routeTestSnapshot(t), req.WithContext(ctx), responsesGateNoContent)
	if rr.Code != http.StatusNoContent {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}

func TestResponsesParseMiddlewareRejectsUnreadableBody(t *testing.T) {
	req := httptest.NewRequest(http.MethodPost, "/v1/responses", nil)
	req.Body = io.NopCloser(errReadCloser{})
	rr := httptest.NewRecorder()
	ResponsesParseMiddleware("")(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { t.Fatal("unreadable body reached handler") })).ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}

type errReadCloser struct{}

func (errReadCloser) Read([]byte) (int, error) { return 0, errors.New("read failure") }
func (errReadCloser) Close() error             { return nil }

func mustWriter(t *testing.T) *billing.UsageFactWriter {
	t.Helper()
	w, _ := newResponsesWriter(t, 100)
	return w
}
