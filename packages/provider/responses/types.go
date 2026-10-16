// Package responses defines the provider-neutral Responses wire contract.
package responses

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
)

// ErrInvalid identifies malformed Requests or Responses payloads.
var ErrInvalid = errors.New("invalid responses payload")

// Reasoning carries provider reasoning controls without translating them to Chat fields.
type Reasoning struct {
	Effort string `json:"effort,omitempty"`
}

// Request is the non-streaming subset accepted by the local Responses adapter.
type Request struct {
	Model              string            `json:"model"`
	Input              json.RawMessage   `json:"input,omitempty"`
	Instructions       string            `json:"instructions,omitempty"`
	MaxOutputTokens    int               `json:"max_output_tokens,omitempty"`
	PreviousResponseID string            `json:"previous_response_id,omitempty"`
	Store              *bool             `json:"store,omitempty"`
	Stream             bool              `json:"stream,omitempty"`
	Reasoning          *Reasoning        `json:"reasoning,omitempty"`
	Tools              []json.RawMessage `json:"tools,omitempty"`
}

// Validate checks semantic request invariants independent of provider capabilities.
func (r Request) Validate() error {
	if r.Model == "" {
		return fmt.Errorf("%w: model is required", ErrInvalid)
	}
	if r.MaxOutputTokens < 0 {
		return fmt.Errorf("%w: max_output_tokens must be non-negative", ErrInvalid)
	}
	if r.Reasoning != nil && r.Reasoning.Effort == "" {
		return fmt.Errorf("%w: reasoning.effort is required when reasoning is present", ErrInvalid)
	}
	return nil
}

// RequiredCapabilities returns manifest claims selected by request fields.
func (r Request) RequiredCapabilities() []string {
	caps := []string{"responses"}
	if r.Reasoning != nil {
		caps = append(caps, "reasoning")
	}
	if len(r.Tools) > 0 {
		caps = append(caps, "tools")
	}
	if r.PreviousResponseID != "" {
		caps = append(caps, "previous_response_id")
	}
	return caps
}

// Usage is the provider-reported token usage for a completed response.
type Usage struct {
	InputTokens  int `json:"input_tokens"`
	OutputTokens int `json:"output_tokens"`
	TotalTokens  int `json:"total_tokens"`
}

func (u Usage) valid() bool {
	return u.InputTokens >= 0 && u.OutputTokens >= 0 && u.TotalTokens >= 0 && u.InputTokens+u.OutputTokens == u.TotalTokens
}

// Response is a parsed, ordered Responses result with its original JSON retained.
type Response struct {
	ID     string          `json:"id"`
	Object string          `json:"object"`
	Status string          `json:"status"`
	Model  string          `json:"model"`
	Output []Item          `json:"output"`
	Usage  *Usage          `json:"usage,omitempty"`
	Raw    json.RawMessage `json:"-"`
}

// Item is a discriminated output item. Raw always retains the exact wire item.
type Item struct {
	Type               string
	Raw                json.RawMessage
	Message            *MessageItem
	Reasoning          *ReasoningItem
	FunctionCall       *FunctionCallItem
	FunctionCallOutput *FunctionCallOutputItem
}
type MessageItem struct {
	ID      string            `json:"id,omitempty"`
	Role    string            `json:"role,omitempty"`
	Content []json.RawMessage `json:"content,omitempty"`
}
type ReasoningItem struct {
	ID               string            `json:"id,omitempty"`
	EncryptedContent string            `json:"encrypted_content,omitempty"`
	Summary          []json.RawMessage `json:"summary,omitempty"`
}
type FunctionCallItem struct {
	ID        string `json:"id,omitempty"`
	CallID    string `json:"call_id"`
	Name      string `json:"name"`
	Arguments string `json:"arguments"`
}
type FunctionCallOutputItem struct {
	CallID string          `json:"call_id"`
	Output json.RawMessage `json:"output"`
}

type responseEnvelope struct {
	ID     string            `json:"id"`
	Object string            `json:"object"`
	Status string            `json:"status"`
	Model  string            `json:"model"`
	Output []json.RawMessage `json:"output"`
	Usage  *Usage            `json:"usage"`
}
type itemDiscriminator struct {
	Type string `json:"type"`
}
type itemDecoder func(json.RawMessage, *Item) error

// ParseResponse validates and decodes the ordered output item union.
func ParseResponse(b []byte) (Response, error) {
	var env responseEnvelope
	if err := json.Unmarshal(b, &env); err != nil {
		return Response{}, fmt.Errorf("%w: %v", ErrInvalid, err)
	}
	out := Response{ID: env.ID, Object: env.Object, Status: env.Status, Model: env.Model, Usage: env.Usage, Raw: append(json.RawMessage(nil), b...)}
	if out.Usage != nil && !out.Usage.valid() {
		return Response{}, fmt.Errorf("%w: inconsistent usage", ErrInvalid)
	}
	out.Output = make([]Item, 0, len(env.Output))
	for _, raw := range env.Output {
		item, err := parseItem(raw)
		if err != nil {
			return Response{}, err
		}
		out.Output = append(out.Output, item)
	}
	return out, nil
}

// parseItem preserves unknown discriminators while decoding known item types.
func parseItem(raw json.RawMessage) (Item, error) {
	var d itemDiscriminator
	if err := json.Unmarshal(raw, &d); err != nil || d.Type == "" {
		return Item{}, fmt.Errorf("%w: output item discriminator", ErrInvalid)
	}
	item := Item{Type: d.Type, Raw: append(json.RawMessage(nil), raw...)}
	decoders := map[string]itemDecoder{"message": decodeMessage, "reasoning": decodeReasoning, "function_call": decodeFunctionCall, "function_call_output": decodeFunctionCallOutput}
	if decode, ok := decoders[d.Type]; ok {
		if err := decode(raw, &item); err != nil {
			return Item{}, err
		}
	}
	return item, nil
}

func decodeMessage(raw json.RawMessage, item *Item) error {
	var v MessageItem
	if err := json.Unmarshal(raw, &v); err != nil {
		return fmt.Errorf("%w: message item: %v", ErrInvalid, err)
	}
	item.Message = &v
	return nil
}
func decodeReasoning(raw json.RawMessage, item *Item) error {
	var v ReasoningItem
	if err := json.Unmarshal(raw, &v); err != nil {
		return fmt.Errorf("%w: reasoning item: %v", ErrInvalid, err)
	}
	item.Reasoning = &v
	return nil
}
func decodeFunctionCall(raw json.RawMessage, item *Item) error {
	var v FunctionCallItem
	if err := json.Unmarshal(raw, &v); err != nil {
		return fmt.Errorf("%w: function call item: %v", ErrInvalid, err)
	}
	item.FunctionCall = &v
	return nil
}
func decodeFunctionCallOutput(raw json.RawMessage, item *Item) error {
	var v FunctionCallOutputItem
	if err := json.Unmarshal(raw, &v); err != nil {
		return fmt.Errorf("%w: function call output item: %v", ErrInvalid, err)
	}
	item.FunctionCallOutput = &v
	return nil
}

// MarshalRequest validates and serializes a request without losing numeric JSON values.
func MarshalRequest(r Request) ([]byte, error) {
	if err := r.Validate(); err != nil {
		return nil, err
	}
	return json.Marshal(r)
}

// DecodeOrderedItems decodes only the ordered output union from a response body.
func DecodeOrderedItems(r io.Reader) ([]Item, error) {
	b, err := io.ReadAll(r)
	if err != nil {
		return nil, err
	}
	var env struct {
		Output []json.RawMessage `json:"output"`
	}
	if err := json.Unmarshal(bytes.TrimSpace(b), &env); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalid, err)
	}
	out := make([]Item, 0, len(env.Output))
	for _, raw := range env.Output {
		v, err := parseItem(raw)
		if err != nil {
			return nil, err
		}
		out = append(out, v)
	}
	return out, nil
}
