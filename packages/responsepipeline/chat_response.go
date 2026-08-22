package responsepipeline

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
)

// ResponseDoc mirrors the OpenAI chat completion response JSON (minimal v1 subset).
type ResponseDoc struct {
	ID      string   `json:"id"`
	Object  string   `json:"object"`
	Created int64    `json:"created"`
	Model   string   `json:"model"`
	Choices []Choice `json:"choices"`
	Usage   *Usage   `json:"usage,omitempty"`
}

// Choice is one completion choice.
type Choice struct {
	Index        int     `json:"index"`
	Message      Message `json:"message"`
	FinishReason string  `json:"finish_reason"`
}

// Message is the assistant message payload in a choice.
type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// Usage holds token counts when present on the upstream response.
type Usage struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
	TotalTokens      int `json:"total_tokens"`
}

var knownTopLevelKeys = map[string]struct{}{
	"id": {}, "object": {}, "created": {}, "model": {}, "choices": {}, "usage": {},
}

// ChatResponse wraps upstream bytes and a typed view for pipeline stages.
type ChatResponse struct {
	raw          []byte
	doc          ResponseDoc
	extra        map[string]json.RawMessage
	dirty        bool
	errOnMarshal error // set only from stage_testsupport.go for marshal-failure tests
}

// Decode validates and parses an OpenAI-shaped chat completion JSON body.
func Decode(body []byte) (*ChatResponse, error) {
	if len(bytes.TrimSpace(body)) == 0 {
		return nil, fmt.Errorf("%w: empty body", ErrInvalidResponse)
	}
	dec := json.NewDecoder(bytes.NewReader(body))
	var envelope map[string]json.RawMessage
	if err := dec.Decode(&envelope); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidResponse, err)
	}
	if err := validateChatCompletionEnvelope(envelope); err != nil {
		return nil, err
	}
	if err := dec.Decode(&struct{}{}); err != io.EOF {
		if err == nil {
			return nil, fmt.Errorf("%w: trailing data", ErrInvalidResponse)
		}
		return nil, fmt.Errorf("%w: %v", ErrInvalidResponse, err)
	}
	var doc ResponseDoc
	if err := json.Unmarshal(body, &doc); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidResponse, err)
	}
	return &ChatResponse{
		raw:   bytes.Clone(body),
		doc:   doc,
		extra: extractExtraFields(envelope),
	}, nil
}

func validateChatCompletionEnvelope(envelope map[string]json.RawMessage) error {
	if envelope == nil {
		return fmt.Errorf("%w: null body", ErrInvalidResponse)
	}
	if len(envelope) == 0 {
		return fmt.Errorf("%w: empty object", ErrInvalidResponse)
	}
	for _, key := range []string{"id", "object", "choices"} {
		raw, ok := envelope[key]
		if !ok {
			return fmt.Errorf("%w: missing required field %q", ErrInvalidResponse, key)
		}
		if bytes.Equal(raw, []byte("null")) {
			return fmt.Errorf("%w: field %q must not be null", ErrInvalidResponse, key)
		}
	}
	return nil
}

func extractExtraFields(envelope map[string]json.RawMessage) map[string]json.RawMessage {
	var extra map[string]json.RawMessage
	for key, value := range envelope {
		if _, known := knownTopLevelKeys[key]; known {
			continue
		}
		if extra == nil {
			extra = make(map[string]json.RawMessage)
		}
		extra[key] = append(json.RawMessage(nil), value...)
	}
	return extra
}

// Doc returns the typed response document for read or in-place mutation.
// Prefer Mutate for edits that must reach the client: in-place changes require
// a matching MarkModified call or Bytes will return stale upstream bytes.
func (c *ChatResponse) Doc() *ResponseDoc {
	if c == nil {
		return nil
	}
	return &c.doc
}

// Mutate applies fn to the typed document and marks the response dirty for re-encode.
func (c *ChatResponse) Mutate(fn func(*ResponseDoc) error) error {
	if c == nil {
		return fmt.Errorf("%w: nil response", ErrInvalidResponse)
	}
	if err := fn(&c.doc); err != nil {
		return err
	}
	c.dirty = true
	return nil
}

// MarkModified signals that stages changed the typed document and re-encode is required.
func (c *ChatResponse) MarkModified() {
	if c != nil {
		c.dirty = true
	}
}

// Bytes returns wire-format JSON for the client. Unmodified responses return upstream
// bytes verbatim. Callers must not mutate the returned slice.
func (c *ChatResponse) Bytes() ([]byte, error) {
	if c == nil {
		return nil, fmt.Errorf("%w: nil response", ErrInvalidResponse)
	}
	if !c.dirty {
		return c.raw, nil
	}
	if c.errOnMarshal != nil {
		return nil, fmt.Errorf("marshal chat response: %w", c.errOnMarshal)
	}
	return c.encodeModified()
}

func (c *ChatResponse) encodeModified() ([]byte, error) {
	base, err := json.Marshal(c.doc)
	if err != nil {
		return nil, fmt.Errorf("marshal chat response: %w", err)
	}
	if len(c.extra) == 0 {
		return base, nil
	}
	var merged map[string]json.RawMessage
	if err := json.Unmarshal(base, &merged); err != nil {
		return nil, fmt.Errorf("marshal chat response: %w", err)
	}
	for key, value := range c.extra {
		if _, exists := merged[key]; !exists {
			merged[key] = value
		}
	}
	out, err := json.Marshal(merged)
	if err != nil {
		return nil, fmt.Errorf("marshal chat response: %w", err)
	}
	return out, nil
}

func (c *ChatResponse) clone() *ChatResponse {
	if c == nil {
		return nil
	}
	cp := &ChatResponse{
		raw:   c.raw,
		doc:   c.doc,
		dirty: c.dirty,
	}
	if len(c.doc.Choices) > 0 {
		cp.doc.Choices = append([]Choice(nil), c.doc.Choices...)
	}
	if c.doc.Usage != nil {
		usage := *c.doc.Usage
		cp.doc.Usage = &usage
	}
	if len(c.extra) > 0 {
		cp.extra = make(map[string]json.RawMessage, len(c.extra))
		for key, value := range c.extra {
			cp.extra[key] = append(json.RawMessage(nil), value...)
		}
	}
	return cp
}
