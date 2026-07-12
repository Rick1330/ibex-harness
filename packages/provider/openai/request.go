package openai

import (
	"encoding/json"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

type openAIRequest struct {
	Model       string          `json:"model"`
	Messages    []openAIMessage `json:"messages"`
	MaxTokens   int             `json:"max_tokens,omitempty"`
	Temperature *float64        `json:"temperature,omitempty"`
	Stream      bool            `json:"stream"`
}

type openAIMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

func toOpenAIRequest(req provider.Request) (openAIRequest, error) {
	out := openAIRequest{
		Model:       req.Model,
		MaxTokens:   req.MaxTokens,
		Temperature: req.Temperature,
		Stream:      req.Stream,
	}
	out.Messages = make([]openAIMessage, len(req.Messages))
	for i, msg := range req.Messages {
		out.Messages[i] = openAIMessage{Role: msg.Role, Content: msg.Content}
	}
	if len(req.PassthroughFields) == 0 {
		return out, nil
	}
	raw, err := json.Marshal(out)
	if err != nil {
		return openAIRequest{}, err
	}
	var merged map[string]any
	if err := json.Unmarshal(raw, &merged); err != nil {
		return openAIRequest{}, err
	}
	for k, v := range req.PassthroughFields {
		merged[k] = v
	}
	raw, err = json.Marshal(merged)
	if err != nil {
		return openAIRequest{}, err
	}
	if err := json.Unmarshal(raw, &out); err != nil {
		return openAIRequest{}, err
	}
	return out, nil
}
