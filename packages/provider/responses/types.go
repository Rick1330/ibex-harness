// Package responses defines the provider-neutral Responses wire contract.
package responses

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
)

var ErrInvalid = errors.New("invalid responses payload")

type Reasoning struct {
	Effort string `json:"effort,omitempty"`
}

type Request struct {
	Model              string            `json:"model"`
	Input              any               `json:"input,omitempty"`
	Instructions       string            `json:"instructions,omitempty"`
	MaxOutputTokens    int               `json:"max_output_tokens,omitempty"`
	PreviousResponseID string            `json:"previous_response_id,omitempty"`
	Store              *bool             `json:"store,omitempty"`
	Stream             bool              `json:"stream,omitempty"`
	Reasoning          *Reasoning        `json:"reasoning,omitempty"`
	Tools              []json.RawMessage `json:"tools,omitempty"`
}

func (r Request) Validate() error {
	if r.Model == "" {
		return fmt.Errorf("%w: model is required", ErrInvalid)
	}
	if r.PreviousResponseID != "" && r.Store != nil && !*r.Store { /* allowed; caller owns replay semantics */
	}
	if r.MaxOutputTokens < 0 {
		return fmt.Errorf("%w: max_output_tokens must be non-negative", ErrInvalid)
	}
	if r.Reasoning != nil && r.Reasoning.Effort == "" {
		return fmt.Errorf("%w: reasoning.effort is required when reasoning is present", ErrInvalid)
	}
	return nil
}

type Response struct {
	ID     string          `json:"id"`
	Object string          `json:"object"`
	Status string          `json:"status"`
	Model  string          `json:"model"`
	Output []Item          `json:"output"`
	Raw    json.RawMessage `json:"-"`
}

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
	CallID string `json:"call_id"`
	Output any    `json:"output"`
}

func ParseResponse(b []byte) (Response, error) {
	var envelope struct {
		ID     string            `json:"id"`
		Object string            `json:"object"`
		Status string            `json:"status"`
		Model  string            `json:"model"`
		Output []json.RawMessage `json:"output"`
	}
	if err := json.Unmarshal(b, &envelope); err != nil {
		return Response{}, fmt.Errorf("%w: %v", ErrInvalid, err)
	}
	out := Response{ID: envelope.ID, Object: envelope.Object, Status: envelope.Status, Model: envelope.Model, Raw: append(json.RawMessage(nil), b...)}
	out.Output = make([]Item, 0, len(envelope.Output))
	for _, raw := range envelope.Output {
		item, err := parseItem(raw)
		if err != nil {
			return Response{}, err
		}
		out.Output = append(out.Output, item)
	}
	return out, nil
}

func parseItem(raw json.RawMessage) (Item, error) {
	var d struct {
		Type string `json:"type"`
	}
	if err := json.Unmarshal(raw, &d); err != nil || d.Type == "" {
		return Item{}, fmt.Errorf("%w: output item discriminator", ErrInvalid)
	}
	item := Item{Type: d.Type, Raw: append(json.RawMessage(nil), raw...)}
	switch d.Type {
	case "message":
		var v MessageItem
		if err := json.Unmarshal(raw, &v); err != nil {
			return Item{}, fmt.Errorf("%w: message item: %v", ErrInvalid, err)
		}
		item.Message = &v
	case "reasoning":
		var v ReasoningItem
		if err := json.Unmarshal(raw, &v); err != nil {
			return Item{}, fmt.Errorf("%w: reasoning item: %v", ErrInvalid, err)
		}
		item.Reasoning = &v
	case "function_call":
		var v FunctionCallItem
		if err := json.Unmarshal(raw, &v); err != nil {
			return Item{}, fmt.Errorf("%w: function call item: %v", ErrInvalid, err)
		}
		item.FunctionCall = &v
	case "function_call_output":
		var v FunctionCallOutputItem
		if err := json.Unmarshal(raw, &v); err != nil {
			return Item{}, fmt.Errorf("%w: function call output item: %v", ErrInvalid, err)
		}
		item.FunctionCallOutput = &v
	}
	return item, nil
}

func MarshalRequest(r Request) ([]byte, error) {
	if err := r.Validate(); err != nil {
		return nil, err
	}
	return json.Marshal(r)
}

func DecodeOrderedItems(r io.Reader) ([]Item, error) {
	b, err := io.ReadAll(r)
	if err != nil {
		return nil, err
	}
	var envelope struct {
		Output []json.RawMessage `json:"output"`
	}
	if err := json.Unmarshal(bytes.TrimSpace(b), &envelope); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalid, err)
	}
	out := make([]Item, 0, len(envelope.Output))
	for _, raw := range envelope.Output {
		v, err := parseItem(raw)
		if err != nil {
			return nil, err
		}
		out = append(out, v)
	}
	return out, nil
}
