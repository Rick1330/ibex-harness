package http

import (
	"context"
	"errors"
	"net/http"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/mockllm"
	"github.com/Rick1330/ibex-harness/packages/responsepipeline"
	"github.com/stretchr/testify/require"
)

const (
	testChoiceCompletionUpstream = `{"id":"x","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"orig"},"finish_reason":"stop"}]}`
	testSecretChoiceUpstream       = `{"id":"x","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"secret"},"finish_reason":"stop"}]}`
	testFingerprintUpstream        = `{"id":"x","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"ok"},"finish_reason":"stop"}],"system_fingerprint":"fp"}`
	testCompletionWithModelJSON    = `{"id":"x","object":"chat.completion","choices":[],"model":"orig"}`
)

type processBodyCase struct {
	name        string
	ctx         context.Context
	pipeline    *responsepipeline.Pipeline
	body        []byte
	wantErr     bool
	wantStatus  int
	wantMsg     string
	wantEqual   []byte
	wantContain string
}

func TestUnit_processResponseBody_scenarios(t *testing.T) {
	t.Parallel()
	mockBody := []byte(mockllm.MockJSONBody())
	cases := []processBodyCase{
		{name: "nil pipeline passthrough", pipeline: nil, body: mockBody, wantEqual: mockBody},
		{name: "noop preserves bytes", pipeline: responsepipeline.NewDefaultPipeline(), body: mockBody, wantEqual: mockBody},
		{name: "invalid JSON", pipeline: responsepipeline.NewDefaultPipeline(), body: []byte("not json"), wantErr: true, wantStatus: http.StatusBadGateway},
		{
			name: "security critical 502", body: mockBody,
			pipeline: responsepipeline.NewPipeline([]responsepipeline.Stage{httpCriticalStage{name: "guard", err: errors.New("blocked")}}),
			wantErr: true, wantStatus: http.StatusBadGateway, wantMsg: errMsgResponsePipelineStageFailed,
		},
		{
			name: "cancelled context", pipeline: responsepipeline.NewDefaultPipeline(), body: mockBody,
			ctx: cancelledContext(), wantErr: true,
		},
		{
			name: "modified stage re-encodes", body: []byte(testChoiceCompletionUpstream),
			pipeline: responsepipeline.NewPipeline([]responsepipeline.Stage{redactContentStage{}}),
			wantContain: "redacted",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runProcessBodyCase(t, tc)
		})
	}
}

func runProcessBodyCase(t *testing.T, tc processBodyCase) {
	t.Helper()
	ctx := tc.ctx
	if ctx == nil {
		ctx = context.Background()
	}
	out, err := chatCompletionHandler{responsePipeline: tc.pipeline}.processResponseBody(ctx, "openai", tc.body)
	if tc.wantErr {
		assertProcessBodyError(t, err, tc.wantStatus, tc.wantMsg)
		return
	}
	require.NoError(t, err)
	if tc.wantEqual != nil {
		require.Equal(t, tc.wantEqual, out)
	}
	if tc.wantContain != "" {
		require.Contains(t, string(out), tc.wantContain)
		require.NotEqual(t, tc.body, out)
	}
}

func assertProcessBodyError(t *testing.T, err error, wantStatus int, wantMsg string) {
	t.Helper()
	require.Error(t, err)
	if wantStatus == 0 && wantMsg == "" {
		return
	}
	var pe *provider.ProviderError
	require.ErrorAs(t, err, &pe)
	if wantStatus != 0 {
		require.Equal(t, wantStatus, pe.StatusCode)
	}
	if wantMsg != "" {
		require.Equal(t, wantMsg, pe.ProviderErrMsg)
		require.NotContains(t, pe.ProviderErrMsg, "blocked")
	}
}

func cancelledContext() context.Context {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	return ctx
}

func TestUnit_ChatCompletions_responsePipelineScenarios(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name            string
		upstream        string
		configure       func(*RouterDeps)
		wantStatus      int
		wantBody        string
		wantContains    []string
		wantNotContains []string
	}{
		{name: "noop byte identical", upstream: mockllm.MockJSONBody(), wantStatus: http.StatusOK, wantBody: mockllm.MockJSONBody()},
		{name: "invalid upstream JSON", upstream: "not json", wantStatus: http.StatusServiceUnavailable},
		{
			name: "security critical maps to 503", upstream: mockllm.MockJSONBody(),
			configure: func(d *RouterDeps) {
				d.ResponsePipeline = responsepipeline.NewPipeline([]responsepipeline.Stage{httpCriticalStage{name: "guard", err: errors.New("blocked")}})
			},
			wantStatus: http.StatusServiceUnavailable, wantContains: []string{string(apierror.CodeProviderUnavailable)},
		},
		{
			name: "modified changes client body", upstream: testSecretChoiceUpstream,
			configure: func(d *RouterDeps) { d.ResponsePipeline = responsepipeline.NewPipeline([]responsepipeline.Stage{redactContentStage{}}) },
			wantStatus: http.StatusOK, wantContains: []string{"redacted"}, wantNotContains: []string{"secret"},
		},
		{
			name: "modified preserves unknown fields", upstream: testFingerprintUpstream,
			configure: func(d *RouterDeps) { d.ResponsePipeline = responsepipeline.NewPipeline([]responsepipeline.Stage{redactContentStage{}}) },
			wantStatus: http.StatusOK, wantContains: []string{"system_fingerprint"},
		},
		{
			name: "fail-open keeps prior stage mutation", upstream: testCompletionWithModelJSON,
			configure: func(d *RouterDeps) {
				d.ResponsePipeline = responsepipeline.NewPipeline([]responsepipeline.Stage{
					setModelStage{model: "kept"}, failAfterMutateStage{name: "fail", revertModel: "reverted"},
				})
			},
			wantStatus: http.StatusOK, wantContains: []string{`"model":"kept"`}, wantNotContains: []string{`"model":"reverted"`},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			rec := postDefaultPipelineChat(t, pipelineChatHandler(t, tc.upstream, tc.configure))
			assertHTTPResponse(t, rec, httpResponseExpect{
				status: tc.wantStatus, body: tc.wantBody, contains: tc.wantContains, notContains: tc.wantNotContains,
			})
		})
	}
}

func TestUnit_Idempotency_responsePipelineReplayParity(t *testing.T) {
	t.Parallel()
	store, _ := testRedisIdempotencyStore(t)
	upstream := mockllm.MockJSONBody()
	prov := &countingLLMProvider{name: "openai", models: []string{"gpt-4o"}, body: upstream}
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), prov)
	require.NoError(t, err)

	cfg := chatTestConfig()
	cfg.IdempotencyTTL = time.Hour
	cfg.IdempotencyRedisTimeout = time.Second
	handler := mustNewRouter(t, mergeRouterDeps(defaultChatRouterDeps(t), func(d *RouterDeps) {
		d.Config = cfg
		d.ProviderRegistry = reg
		d.IdempotencyStore = store
	}))

	opts := chatRequestOpts{body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: "pipeline-key-1"}
	rec1 := postChat(t, handler, opts)
	require.Equal(t, http.StatusOK, rec1.Code)
	require.Equal(t, upstream, rec1.Body.String())

	rec2 := postChat(t, handler, opts)
	require.Equal(t, http.StatusOK, rec2.Code)
	require.Equal(t, rec1.Body.String(), rec2.Body.String())
	require.Equal(t, int64(1), prov.calls.Load())
}

type redactContentStage struct{}

func (redactContentStage) Name() string { return "mutate" }

func (redactContentStage) Process(_ context.Context, resp *responsepipeline.ChatResponse) (*responsepipeline.ChatResponse, error) {
	return mutateFirstChoiceContent(resp, "redacted")
}

type setModelStage struct{ model string }

func (s setModelStage) Name() string { return "model" }

func (s setModelStage) Process(_ context.Context, resp *responsepipeline.ChatResponse) (*responsepipeline.ChatResponse, error) {
	return mutateModel(resp, s.model)
}

type failAfterMutateStage struct {
	name        string
	revertModel string
}

func (s failAfterMutateStage) Name() string { return s.name }

func (s failAfterMutateStage) Process(_ context.Context, resp *responsepipeline.ChatResponse) (*responsepipeline.ChatResponse, error) {
	if _, err := mutateModel(resp, s.revertModel); err != nil {
		return nil, err
	}
	return nil, errors.New("fail-open")
}

type httpCriticalStage struct {
	name string
	err  error
}

func (s httpCriticalStage) Name() string { return s.name }

func (s httpCriticalStage) Process(_ context.Context, _ *responsepipeline.ChatResponse) (*responsepipeline.ChatResponse, error) {
	return nil, s.err
}

func (httpCriticalStage) SecurityCritical() bool { return true }

func mutateModel(resp *responsepipeline.ChatResponse, model string) (*responsepipeline.ChatResponse, error) {
	if err := resp.Mutate(func(doc *responsepipeline.ResponseDoc) error { doc.Model = model; return nil }); err != nil {
		return nil, err
	}
	return resp, nil
}

func mutateFirstChoiceContent(resp *responsepipeline.ChatResponse, content string) (*responsepipeline.ChatResponse, error) {
	if err := resp.Mutate(func(doc *responsepipeline.ResponseDoc) error {
		if len(doc.Choices) > 0 {
			doc.Choices[0].Message.Content = content
		}
		return nil
	}); err != nil {
		return nil, err
	}
	return resp, nil
}
