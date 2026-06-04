package llm

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
)

// ErrInvalidJSON indicates the request body is not valid OpenAI-shaped JSON.
var ErrInvalidJSON = errors.New("invalid json")

// Message is one chat message (content is never logged).
type Message struct {
	Role    string
	Content string
}

// ChatCompletionRequest is the normalized OpenAI-compatible chat body (minimal subset).
type ChatCompletionRequest struct {
	Model       string
	Messages    []Message
	Stream      bool
	Temperature *float64
	MaxTokens   *int
}

type wireRequest struct {
	Model       string          `json:"model"`
	Messages    json.RawMessage `json:"messages"`
	Stream      *bool           `json:"stream"`
	Temperature *float64        `json:"temperature"`
	MaxTokens   *int            `json:"max_tokens"`
}

type wireMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// ParseChatCompletionRequest decodes an OpenAI-compatible chat completion body.
// Unknown top-level fields are ignored. Semantic validation is deferred to milestone 1.2.3.
func ParseChatCompletionRequest(r io.Reader) (*ChatCompletionRequest, error) {
	dec := json.NewDecoder(r)
	var wire wireRequest
	if err := dec.Decode(&wire); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidJSON, err)
	}
	if err := dec.Decode(&struct{}{}); err != io.EOF {
		if err == nil {
			return nil, fmt.Errorf("%w: trailing data", ErrInvalidJSON)
		}
		return nil, fmt.Errorf("%w: %v", ErrInvalidJSON, err)
	}

	out := &ChatCompletionRequest{
		Model:       wire.Model,
		Stream:      wire.Stream != nil && *wire.Stream,
		Temperature: wire.Temperature,
		MaxTokens:   wire.MaxTokens,
	}

	if len(wire.Messages) == 0 {
		return out, nil
	}
	if wire.Messages[0] != '[' {
		return nil, fmt.Errorf("%w: messages must be a JSON array", ErrInvalidJSON)
	}
	var rawMsgs []json.RawMessage
	if err := json.Unmarshal(wire.Messages, &rawMsgs); err != nil {
		return nil, fmt.Errorf("%w: messages must be a JSON array", ErrInvalidJSON)
	}
	for i, raw := range rawMsgs {
		if len(raw) == 0 || raw[0] != '{' {
			return nil, fmt.Errorf("%w: messages[%d] must be an object", ErrInvalidJSON, i)
		}
		var wm wireMessage
		if err := json.Unmarshal(raw, &wm); err != nil {
			return nil, fmt.Errorf("%w: messages[%d]: %v", ErrInvalidJSON, i, err)
		}
		out.Messages = append(out.Messages, Message(wm))
	}
	return out, nil
}
