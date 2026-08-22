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

func TestUnit_processResponseBody_nilPipelineReturnsOriginal(t *testing.T) {
	t.Parallel()
	body := []byte(mockllm.MockJSONBody())
	h := chatCompletionHandler{responsePipeline: nil}
	out, err := h.processResponseBody(context.Background(), "openai", body)
	require.NoError(t, err)
	require.Equal(t, body, out)
}

func TestUnit_processResponseBody_invalidJSON(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{responsePipeline: responsepipeline.NewDefaultPipeline()}
	_, err := h.processResponseBody(context.Background(), "openai", []byte("not json"))
	require.Error(t, err)
	var pe *provider.ProviderError
	require.ErrorAs(t, err, &pe)
	require.Equal(t, http.StatusBadGateway, pe.StatusCode)
}

func TestUnit_processResponseBody_noopPreservesBytes(t *testing.T) {
	t.Parallel()
	body := []byte(mockllm.MockJSONBody())
	h := chatCompletionHandler{responsePipeline: responsepipeline.NewDefaultPipeline()}
	out, err := h.processResponseBody(context.Background(), "openai", body)
	require.NoError(t, err)
	require.Equal(t, body, out)
}

func TestUnit_processResponseBody_securityCriticalReturnsProviderError502(t *testing.T) {
	t.Parallel()
	body := []byte(mockllm.MockJSONBody())
	h := chatCompletionHandler{
		responsePipeline: responsepipeline.NewPipeline([]responsepipeline.Stage{httpCriticalStage{
			name: "guard", err: errors.New("blocked"),
		}}),
	}
	_, err := h.processResponseBody(context.Background(), "openai", body)
	require.Error(t, err)
	var pe *provider.ProviderError
	require.ErrorAs(t, err, &pe)
	require.Equal(t, http.StatusBadGateway, pe.StatusCode)
	require.Equal(t, errMsgResponsePipelineStageFailed, pe.ProviderErrMsg)
	require.NotContains(t, pe.ProviderErrMsg, "blocked")
}

func TestUnit_processResponseBody_cancelledContext(t *testing.T) {
	t.Parallel()
	body := []byte(mockllm.MockJSONBody())
	h := chatCompletionHandler{responsePipeline: responsepipeline.NewDefaultPipeline()}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := h.processResponseBody(ctx, "openai", body)
	require.Error(t, err)
	var pe *provider.ProviderError
	require.ErrorAs(t, err, &pe)
}

func TestUnit_processResponseBody_modifiedStageReturnsReEncodedBody(t *testing.T) {
	t.Parallel()
	body := []byte(testChoiceCompletionUpstream)
	h := chatCompletionHandler{
		responsePipeline: responsepipeline.NewPipeline([]responsepipeline.Stage{httpMutateStage{}}),
	}
	out, err := h.processResponseBody(context.Background(), "openai", body)
	require.NoError(t, err)
	require.Contains(t, string(out), "redacted")
	require.NotEqual(t, body, out)
}

func TestUnit_ChatCompletions_responsePipelineNoopByteIdentical(t *testing.T) {
	t.Parallel()
	upstream := mockllm.MockJSONBody()
	handler := pipelineChatHandler(t, upstream, nil)
	rec := postDefaultPipelineChat(t, handler)
	require.Equal(t, http.StatusOK, rec.Code)
	require.Equal(t, upstream, rec.Body.String())
}

func TestUnit_ChatCompletions_responsePipelineInvalidUpstreamJSON(t *testing.T) {
	t.Parallel()
	handler := pipelineChatHandler(t, "not json", nil)
	rec := postDefaultPipelineChat(t, handler)
	require.Equal(t, http.StatusServiceUnavailable, rec.Code)
}

func TestUnit_ChatCompletions_responsePipelineSecurityCriticalMapsTo503Envelope(t *testing.T) {
	t.Parallel()
	handler := pipelineChatHandler(t, mockllm.MockJSONBody(), func(d *RouterDeps) {
		d.ResponsePipeline = responsepipeline.NewPipeline([]responsepipeline.Stage{httpCriticalStage{
			name: "guard", err: errors.New("blocked"),
		}})
	})
	rec := postDefaultPipelineChat(t, handler)
	require.Equal(t, http.StatusServiceUnavailable, rec.Code)
	require.Contains(t, rec.Body.String(), string(apierror.CodeProviderUnavailable))
}

func TestUnit_ChatCompletions_responsePipelineModifiedChangesClientBody(t *testing.T) {
	t.Parallel()
	handler := pipelineChatHandler(t, testSecretChoiceUpstream, func(d *RouterDeps) {
		d.ResponsePipeline = responsepipeline.NewPipeline([]responsepipeline.Stage{httpMutateStage{}})
	})
	rec := postDefaultPipelineChat(t, handler)
	require.Equal(t, http.StatusOK, rec.Code)
	require.Contains(t, rec.Body.String(), "redacted")
	require.NotContains(t, rec.Body.String(), "secret")
}

func TestUnit_ChatCompletions_responsePipelineModifiedPreservesUnknownFields(t *testing.T) {
	t.Parallel()
	handler := pipelineChatHandler(t, testFingerprintUpstream, func(d *RouterDeps) {
		d.ResponsePipeline = responsepipeline.NewPipeline([]responsepipeline.Stage{httpMutateStage{}})
	})
	rec := postDefaultPipelineChat(t, handler)
	require.Equal(t, http.StatusOK, rec.Code)
	require.Contains(t, rec.Body.String(), "system_fingerprint")
}

func TestUnit_ChatCompletions_responsePipelineFailOpenTwoStagePartialMutation(t *testing.T) {
	t.Parallel()
	handler := pipelineChatHandler(t, testCompletionWithModelJSON, func(d *RouterDeps) {
		d.ResponsePipeline = responsepipeline.NewPipeline([]responsepipeline.Stage{
			httpModelStage{model: "kept"},
			httpFailStage{name: "fail"},
		})
	})
	rec := postDefaultPipelineChat(t, handler)
	require.Equal(t, http.StatusOK, rec.Code)
	require.Contains(t, rec.Body.String(), `"model":"kept"`)
	require.NotContains(t, rec.Body.String(), `"model":"reverted"`)
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

	opts := chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: "pipeline-key-1",
	}
	rec1 := postChat(t, handler, opts)
	require.Equal(t, http.StatusOK, rec1.Code)
	require.Equal(t, upstream, rec1.Body.String())

	rec2 := postChat(t, handler, opts)
	require.Equal(t, http.StatusOK, rec2.Code)
	require.Equal(t, rec1.Body.String(), rec2.Body.String())
	require.Equal(t, int64(1), prov.calls.Load())
}

type httpMutateStage struct{}

func (httpMutateStage) Name() string { return "mutate" }

func (httpMutateStage) Process(_ context.Context, resp *responsepipeline.ChatResponse) (*responsepipeline.ChatResponse, error) {
	if err := resp.Mutate(func(doc *responsepipeline.ResponseDoc) error {
		if len(doc.Choices) > 0 {
			doc.Choices[0].Message.Content = "redacted"
		}
		return nil
	}); err != nil {
		return nil, err
	}
	return resp, nil
}

type httpModelStage struct {
	model string
}

func (s httpModelStage) Name() string { return "model" }

func (s httpModelStage) Process(_ context.Context, resp *responsepipeline.ChatResponse) (*responsepipeline.ChatResponse, error) {
	if err := resp.Mutate(func(doc *responsepipeline.ResponseDoc) error {
		doc.Model = s.model
		return nil
	}); err != nil {
		return nil, err
	}
	return resp, nil
}

type httpFailStage struct {
	name string
}

func (s httpFailStage) Name() string { return s.name }

func (s httpFailStage) Process(_ context.Context, resp *responsepipeline.ChatResponse) (*responsepipeline.ChatResponse, error) {
	if err := resp.Mutate(func(doc *responsepipeline.ResponseDoc) error {
		doc.Model = "reverted"
		return nil
	}); err != nil {
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
