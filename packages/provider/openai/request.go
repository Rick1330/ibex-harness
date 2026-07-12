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

var deniedPassthroughKeys = map[string]struct{}{
	"model": {}, "messages": {}, "stream": {},
	"max_tokens": {}, "temperature": {},
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
	return out, nil
}

func marshalOpenAIRequestBody(req provider.Request) ([]byte, error) {
	out, err := toOpenAIRequest(req)
	if err != nil {
		return nil, err
	}
	if len(req.PassthroughFields) == 0 {
		return json.Marshal(out)
	}
	raw, err := json.Marshal(out)
	if err != nil {
		return nil, err
	}
	var merged map[string]any
	if err := json.Unmarshal(raw, &merged); err != nil {
		return nil, err
	}
	for k, v := range req.PassthroughFields {
		if _, denied := deniedPassthroughKeys[k]; denied {
			continue
		}
		merged[k] = v
	}
	return json.Marshal(merged)
}
