package anthropic

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

type anthropicMessageResponse struct {
	ID         string             `json:"id"`
	Type       string             `json:"type"`
	Role       string             `json:"role"`
	Content    []anthropicContent `json:"content"`
	Model      string             `json:"model"`
	StopReason string             `json:"stop_reason"`
	Usage      anthropicUsage     `json:"usage"`
}

type anthropicContent struct {
	Type string `json:"type"`
	Text string `json:"text"`
}

type anthropicUsage struct {
	InputTokens  int `json:"input_tokens"`
	OutputTokens int `json:"output_tokens"`
}

type openAIChatCompletion struct {
	ID      string         `json:"id"`
	Object  string         `json:"object"`
	Created int64          `json:"created"`
	Model   string         `json:"model"`
	Choices []openAIChoice `json:"choices"`
	Usage   openAIUsage    `json:"usage"`
}

type openAIChoice struct {
	Index        int           `json:"index"`
	Message      openAIMessage `json:"message"`
	FinishReason string        `json:"finish_reason"`
}

type openAIMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type openAIUsage struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
	TotalTokens      int `json:"total_tokens"`
}

func translateNonStreamResponse(raw []byte, requestModel string, requestID string, latency time.Duration) (provider.Response, error) {
	anth, err := decodeAnthropicMessage(raw)
	if err != nil {
		return provider.Response{}, err
	}
	out := buildOpenAICompletion(anth, requestModel)
	body, err := json.Marshal(out)
	if err != nil {
		return provider.Response{}, err
	}
	if requestID == "" {
		requestID = out.ID
	}
	return provider.Response{
		Body:       io.NopCloser(bytes.NewReader(body)),
		StatusCode: http.StatusOK,
		Usage: &provider.Usage{
			InputTokens:  anth.Usage.InputTokens,
			OutputTokens: anth.Usage.OutputTokens,
			TotalTokens:  out.Usage.TotalTokens,
		},
		Latency:           latency,
		ProviderRequestID: requestID,
	}, nil
}

func decodeAnthropicMessage(raw []byte) (anthropicMessageResponse, error) {
	var anth anthropicMessageResponse
	if err := json.Unmarshal(raw, &anth); err != nil {
		return anthropicMessageResponse{}, &provider.ProviderError{
			ProviderName:   "anthropic",
			StatusCode:     http.StatusBadGateway,
			ProviderErrMsg: "invalid anthropic response JSON",
			ProviderBody:   raw,
		}
	}
	return anth, nil
}

func buildOpenAICompletion(anth anthropicMessageResponse, requestModel string) openAIChatCompletion {
	model := anth.Model
	if model == "" {
		model = requestModel
	}
	id := anth.ID
	if id == "" {
		id = newFallbackCompletionID()
	}
	usage := openAIUsage{
		PromptTokens:     anth.Usage.InputTokens,
		CompletionTokens: anth.Usage.OutputTokens,
		TotalTokens:      anth.Usage.InputTokens + anth.Usage.OutputTokens,
	}
	return openAIChatCompletion{
		ID:      id,
		Object:  "chat.completion",
		Created: time.Now().Unix(),
		Model:   model,
		Choices: []openAIChoice{{
			Index: 0,
			Message: openAIMessage{
				Role:    "assistant",
				Content: concatTextBlocks(anth.Content),
			},
			FinishReason: mapStopReason(anth.StopReason),
		}},
		Usage: usage,
	}
}

func concatTextBlocks(blocks []anthropicContent) string {
	var b strings.Builder
	for _, block := range blocks {
		if block.Type != "" && block.Type != "text" {
			continue
		}
		b.WriteString(block.Text)
	}
	return b.String()
}

func mapStopReason(reason string) string {
	switch strings.ToLower(strings.TrimSpace(reason)) {
	case "max_tokens":
		return "length"
	case "end_turn", "stop_sequence", "":
		return "stop"
	default:
		return "stop"
	}
}
