package responsepipeline

import (
	"context"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider/mockllm"
	"github.com/stretchr/testify/require"
)

func TestUnit_Decode_AcceptsMockProviderBody(t *testing.T) {
	body := []byte(mockllm.MockJSONBody())
	resp, err := Decode(body)
	require.NoError(t, err)
	require.Equal(t, "mock", resp.Doc().ID)
	require.Equal(t, "ok", resp.Doc().Choices[0].Message.Content)
	out, err := resp.Bytes()
	require.NoError(t, err)
	require.Equal(t, body, out)
}

func TestUnit_Decode_AcceptsUnknownTopLevelFields(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[],"system_fingerprint":"fp","usage":{"prompt_tokens":1,"completion_tokens":0,"total_tokens":1}}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	out, err := resp.Bytes()
	require.NoError(t, err)
	require.Equal(t, body, out)
}

func TestUnit_Decode_RejectsInvalidJSON(t *testing.T) {
	_, err := Decode([]byte("not-json"))
	require.ErrorIs(t, err, ErrInvalidResponse)
}

func TestUnit_Decode_RejectsEmptyBody(t *testing.T) {
	_, err := Decode([]byte("  "))
	require.ErrorIs(t, err, ErrInvalidResponse)
}

func TestUnit_Decode_RejectsTrailingData(t *testing.T) {
	_, err := Decode([]byte(`{"id":"x","object":"chat.completion","choices":[]}{}`))
	require.ErrorIs(t, err, ErrInvalidResponse)
}

func TestUnit_Decode_RejectsNonObjectTrailingJSON(t *testing.T) {
	_, err := Decode([]byte(`{"id":"x","object":"chat.completion","choices":[]}trailing`))
	require.ErrorIs(t, err, ErrInvalidResponse)
}

func TestUnit_NoopPipeline_ByteIdenticalFixtures(t *testing.T) {
	fixtures := [][]byte{
		[]byte(mockllm.MockJSONBody()),
		[]byte(`{"id":"anth","object":"chat.completion","created":1,"model":"claude-sonnet-4-5","choices":[{"index":0,"message":{"role":"assistant","content":"hi"},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":1,"total_tokens":4}}`),
	}
	pipe := NewDefaultPipeline()
	for _, body := range fixtures {
		resp, err := Decode(body)
		require.NoError(t, err)
		out, err := pipe.Run(context.Background(), resp)
		require.NoError(t, err)
		wire, err := out.Bytes()
		require.NoError(t, err)
		require.Equal(t, body, wire)
	}
}

func TestUnit_Pipeline_RunsStagesInOrder(t *testing.T) {
	var order []string
	s1 := stubStage{name: "first", fn: func(resp *ChatResponse) (*ChatResponse, error) {
		order = append(order, "first")
		require.NoError(t, resp.Mutate(func(doc *ResponseDoc) error {
			doc.Model = "m1"
			return nil
		}))
		return resp, nil
	}}
	s2 := stubStage{name: "second", fn: func(resp *ChatResponse) (*ChatResponse, error) {
		order = append(order, "second")
		require.NoError(t, resp.Mutate(func(doc *ResponseDoc) error {
			doc.Model = "m2"
			return nil
		}))
		return resp, nil
	}}
	body := []byte(`{"id":"x","object":"chat.completion","choices":[],"model":"orig"}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	out, err := NewPipeline([]Stage{s1, s2}).Run(context.Background(), resp)
	require.NoError(t, err)
	require.Equal(t, []string{"first", "second"}, order)
	require.Equal(t, "m2", out.Doc().Model)
}

func TestUnit_Pipeline_FailOpenOnStageError(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	out, err := NewPipeline([]Stage{stubStage{
		name: "fail",
		fn:   func(*ChatResponse) (*ChatResponse, error) { return nil, errors.New("stage failed") },
	}}).Run(context.Background(), resp)
	require.NoError(t, err)
	wire, err := out.Bytes()
	require.NoError(t, err)
	require.Equal(t, body, wire)
}

func TestUnit_Pipeline_FailClosedOnSecurityCritical(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	wantErr := errors.New("critical failure")
	_, err = NewPipeline([]Stage{criticalStubStage{stubStage{
		name: "guard",
		fn:   func(*ChatResponse) (*ChatResponse, error) { return nil, wantErr },
	}}}).Run(context.Background(), resp)
	require.ErrorIs(t, err, wantErr)
}

func TestUnit_Pipeline_LogsFailOpenErrors(t *testing.T) {
	var logged bool
	log := stubLogger{fn: func(_ context.Context, stage string, err error) {
		logged = true
		require.Equal(t, "fail", stage)
		require.Error(t, err)
	}}
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	_, runErr := NewPipeline([]Stage{stubStage{
		name: "fail",
		fn:   func(*ChatResponse) (*ChatResponse, error) { return nil, errors.New("boom") },
	}}, WithStageLogger(log)).Run(context.Background(), resp)
	require.NoError(t, runErr)
	require.True(t, logged)
}

func TestUnit_Pipeline_NilReceiverPassthrough(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	var p *Pipeline
	out, err := p.Run(context.Background(), resp)
	require.NoError(t, err)
	require.Same(t, resp, out)
}

func TestUnit_Pipeline_EmptyStagesPassthrough(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	out, err := NewPipeline(nil).Run(context.Background(), resp)
	require.NoError(t, err)
	require.Same(t, resp, out)
}

func TestUnit_Pipeline_CancelledContextBeforeStage(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = NewDefaultPipeline().Run(ctx, resp)
	require.ErrorIs(t, err, context.Canceled)
}

func TestUnit_Pipeline_CancelledContextBetweenStages(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	s1 := stubStage{name: "first", fn: func(r *ChatResponse) (*ChatResponse, error) {
		cancel()
		return r, nil
	}}
	_, err = NewPipeline([]Stage{s1, stubStage{name: "second", fn: func(r *ChatResponse) (*ChatResponse, error) {
		return r, nil
	}}}).Run(ctx, resp)
	require.ErrorIs(t, err, context.Canceled)
}

func TestUnit_Pipeline_StageReturnsNilKeepsCurrent(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	out, err := NewPipeline([]Stage{stubStage{
		name: "nil-return",
		fn:   func(r *ChatResponse) (*ChatResponse, error) { return nil, nil },
	}}).Run(context.Background(), resp)
	require.NoError(t, err)
	require.Same(t, resp, out)
}

func TestUnit_Decode_RejectsNullBody(t *testing.T) {
	_, err := Decode([]byte("null"))
	require.ErrorIs(t, err, ErrInvalidResponse)
}

func TestUnit_Decode_RejectsEmptyObject(t *testing.T) {
	_, err := Decode([]byte("{}"))
	require.ErrorIs(t, err, ErrInvalidResponse)
}

func TestUnit_Decode_RejectsMissingRequiredFields(t *testing.T) {
	_, err := Decode([]byte(`{"object":"chat.completion","choices":[]}`))
	require.ErrorIs(t, err, ErrInvalidResponse)
}

func TestUnit_Decode_RejectsNullRequiredField(t *testing.T) {
	_, err := Decode([]byte(`{"id":null,"object":"chat.completion","choices":[]}`))
	require.ErrorIs(t, err, ErrInvalidResponse)
}

func TestUnit_Pipeline_FailOpenSnapshotPreservesExtraFields(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[],"model":"orig","system_fingerprint":"fp","usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	out, err := NewPipeline([]Stage{
		stubStage{name: "mutate", fn: func(r *ChatResponse) (*ChatResponse, error) {
			require.NoError(t, r.Mutate(func(doc *ResponseDoc) error {
				doc.Model = "edited"
				return nil
			}))
			return r, nil
		}},
		stubStage{name: "fail", fn: func(*ChatResponse) (*ChatResponse, error) {
			return nil, errors.New("boom")
		}},
	}).Run(context.Background(), resp)
	require.NoError(t, err)
	wire, err := out.Bytes()
	require.NoError(t, err)
	require.Contains(t, string(wire), `"model":"edited"`)
	require.Contains(t, string(wire), "system_fingerprint")
}

func TestUnit_Pipeline_FailOpenRevertsFailingStageMutation(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"orig"},"finish_reason":"stop"}]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	out, err := NewPipeline([]Stage{stubStage{
		name: "mutate-and-fail",
		fn: func(r *ChatResponse) (*ChatResponse, error) {
			require.NoError(t, r.Mutate(func(doc *ResponseDoc) error {
				doc.Choices[0].Message.Content = "partial"
				return nil
			}))
			return nil, errors.New("boom")
		},
	}}).Run(context.Background(), resp)
	require.NoError(t, err)
	wire, err := out.Bytes()
	require.NoError(t, err)
	require.Equal(t, body, wire)
}

func TestUnit_Pipeline_FailOpenPreservesPriorStageMutation(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[],"model":"orig"}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	out, err := NewPipeline([]Stage{
		stubStage{name: "mutate", fn: func(r *ChatResponse) (*ChatResponse, error) {
			require.NoError(t, r.Mutate(func(doc *ResponseDoc) error {
				doc.Model = "edited"
				return nil
			}))
			return r, nil
		}},
		stubStage{name: "fail", fn: func(*ChatResponse) (*ChatResponse, error) {
			return nil, errors.New("fail")
		}},
	}).Run(context.Background(), resp)
	require.NoError(t, err)
	wire, err := out.Bytes()
	require.NoError(t, err)
	require.Contains(t, string(wire), `"model":"edited"`)
}

func TestUnit_Pipeline_SecurityCriticalFalseFailsOpen(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	out, err := NewPipeline([]Stage{nonCriticalStubStage{stubStage{
		name: "soft-fail",
		fn:   func(*ChatResponse) (*ChatResponse, error) { return nil, errors.New("soft") },
	}}}).Run(context.Background(), resp)
	require.NoError(t, err)
	wire, err := out.Bytes()
	require.NoError(t, err)
	require.Equal(t, body, wire)
}

func TestUnit_Pipeline_ObserverRecordsFailOpen(t *testing.T) {
	obs := &stubObserver{}
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	_, err = NewPipeline([]Stage{stubStage{
		name: "fail",
		fn:   func(*ChatResponse) (*ChatResponse, error) { return nil, errors.New("boom") },
	}}, WithPipelineObserver(obs)).Run(context.Background(), resp)
	require.NoError(t, err)
	require.Equal(t, 1, obs.failOpen["fail"])
	require.Equal(t, stageResultFailOpen, obs.lastResult)
}

func TestUnit_Pipeline_ObserverRecordsStageDuration(t *testing.T) {
	obs := &stubObserver{}
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	_, err = NewDefaultPipeline(WithPipelineObserver(obs)).Run(context.Background(), resp)
	require.NoError(t, err)
	require.Equal(t, stageResultSuccess, obs.lastResult)
	require.Equal(t, "noop", obs.lastStage)
	require.GreaterOrEqual(t, obs.lastSeconds, 0.0)
}

func TestUnit_ChatResponse_MutateSetsDirtyAndReEncodes(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[],"model":"orig"}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	require.NoError(t, resp.Mutate(func(doc *ResponseDoc) error {
		doc.Model = "new"
		return nil
	}))
	wire, err := resp.Bytes()
	require.NoError(t, err)
	require.NotEqual(t, body, wire)
	require.Contains(t, string(wire), `"model":"new"`)
}

func TestUnit_ChatResponse_DocMutationWithoutMarkModifiedReturnsRaw(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[],"model":"orig"}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	resp.Doc().Model = "silent"
	wire, err := resp.Bytes()
	require.NoError(t, err)
	require.Equal(t, body, wire)
}

func TestUnit_ChatResponse_ModifiedReEncodePreservesUnknownFields(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[],"model":"orig","system_fingerprint":"fp"}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	require.NoError(t, resp.Mutate(func(doc *ResponseDoc) error {
		doc.Model = "new"
		return nil
	}))
	wire, err := resp.Bytes()
	require.NoError(t, err)
	require.Contains(t, string(wire), "system_fingerprint")
	require.Contains(t, string(wire), `"model":"new"`)
}

func TestUnit_ChatResponse_NilReceiverErrors(t *testing.T) {
	var resp *ChatResponse
	require.Nil(t, resp.Doc())
	_, err := resp.Bytes()
	require.ErrorIs(t, err, ErrInvalidResponse)
	require.ErrorIs(t, resp.Mutate(func(*ResponseDoc) error { return nil }), ErrInvalidResponse)
}

func TestUnit_ChatResponse_BytesUnmodifiedAliasesRaw(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	a, err := resp.Bytes()
	require.NoError(t, err)
	b, err := resp.Bytes()
	require.NoError(t, err)
	require.Equal(t, body, a)
	require.Equal(t, body, b)
	if len(a) > 0 {
		require.Equal(t, &a[0], &b[0])
	}
}

func TestUnit_NoopStage_Name(t *testing.T) {
	require.Equal(t, "noop", NoopStage{}.Name())
}

func TestUnit_ChatResponse_MarkModifiedReEncodes(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[],"model":"orig"}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	resp.Doc().Model = "marked"
	resp.MarkModified()
	wire, err := resp.Bytes()
	require.NoError(t, err)
	require.Contains(t, string(wire), `"model":"marked"`)
}

func TestUnit_ChatResponse_MutateFnErrorLeavesClean(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[],"model":"orig"}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	err = resp.Mutate(func(*ResponseDoc) error { return errors.New("mutate failed") })
	require.Error(t, err)
	wire, err := resp.Bytes()
	require.NoError(t, err)
	require.Equal(t, body, wire)
}

func TestUnit_ChatResponse_CloneCopiesUsage(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[],"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	cp := resp.clone()
	require.NotNil(t, cp.Doc().Usage)
	require.Equal(t, 3, cp.Doc().Usage.TotalTokens)
	cp.Doc().Usage.TotalTokens = 99
	require.Equal(t, 3, resp.Doc().Usage.TotalTokens)
}

func TestUnit_ForceBytesErrorStage_BytesFails(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	out, err := NewPipeline([]Stage{MarshalFailStageForTest()}).Run(context.Background(), resp)
	require.NoError(t, err)
	_, err = out.Bytes()
	require.Error(t, err)
}

func TestUnit_Pipeline_FailOpenContinuesToLaterSecurityCriticalStage(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[]}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	wantErr := errors.New("guard blocked")
	_, err = NewPipeline([]Stage{
		stubStage{name: "mutate", fn: func(r *ChatResponse) (*ChatResponse, error) {
			require.NoError(t, r.Mutate(func(doc *ResponseDoc) error {
				doc.Model = "kept"
				return nil
			}))
			return r, nil
		}},
		stubStage{name: "fail-open", fn: func(*ChatResponse) (*ChatResponse, error) {
			return nil, errors.New("soft fail")
		}},
		criticalStubStage{stubStage{
			name: "guard",
			fn:   func(*ChatResponse) (*ChatResponse, error) { return nil, wantErr },
		}},
	}).Run(context.Background(), resp)
	require.ErrorIs(t, err, wantErr)
}

func TestUnit_Pipeline_FailOpenContinuesToLaterNonCriticalStage(t *testing.T) {
	body := []byte(`{"id":"x","object":"chat.completion","choices":[],"model":"orig"}`)
	resp, err := Decode(body)
	require.NoError(t, err)
	var thirdRan bool
	out, err := NewPipeline([]Stage{
		stubStage{name: "mutate", fn: func(r *ChatResponse) (*ChatResponse, error) {
			require.NoError(t, r.Mutate(func(doc *ResponseDoc) error {
				doc.Model = "kept"
				return nil
			}))
			return r, nil
		}},
		stubStage{name: "fail-open", fn: func(*ChatResponse) (*ChatResponse, error) {
			return nil, errors.New("soft fail")
		}},
		stubStage{name: "third", fn: func(r *ChatResponse) (*ChatResponse, error) {
			thirdRan = true
			require.NoError(t, r.Mutate(func(doc *ResponseDoc) error {
				doc.Model = "final"
				return nil
			}))
			return r, nil
		}},
	}).Run(context.Background(), resp)
	require.NoError(t, err)
	require.True(t, thirdRan)
	require.Equal(t, "final", out.Doc().Model)
}

type stubStage struct {
	name string
	fn   func(*ChatResponse) (*ChatResponse, error)
}

func (s stubStage) Name() string { return s.name }

func (s stubStage) Process(_ context.Context, resp *ChatResponse) (*ChatResponse, error) {
	return s.fn(resp)
}

type criticalStubStage struct {
	stubStage
}

func (criticalStubStage) SecurityCritical() bool { return true }

type nonCriticalStubStage struct {
	stubStage
}

func (nonCriticalStubStage) SecurityCritical() bool { return false }

type stubLogger struct {
	fn func(context.Context, string, error)
}

func (s stubLogger) WarnStageError(ctx context.Context, stage string, err error) {
	s.fn(ctx, stage, err)
}

type stubObserver struct {
	lastStage   string
	lastResult  string
	lastSeconds float64
	failOpen    map[string]int
}

func (s *stubObserver) ObserveStageDuration(stage, result string, seconds float64) {
	s.lastStage = stage
	s.lastResult = result
	s.lastSeconds = seconds
}

func (s *stubObserver) IncStageFailOpen(stage string) {
	if s.failOpen == nil {
		s.failOpen = make(map[string]int)
	}
	s.failOpen[stage]++
}
