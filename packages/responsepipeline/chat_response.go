package responsepipeline

import (
	"bytes"
	"encoding/json"
	"errors"
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

// ChatResponse wraps upstream bytes and a typed view for pipeline stages.
type ChatResponse struct {
	raw           []byte
	doc           ResponseDoc
	dirty         bool
	forceBytesErr bool // test-only: ForceBytesErrorStage
}

// Decode validates and parses an OpenAI-shaped chat completion JSON body.
func Decode(body []byte) (*ChatResponse, error) {
	if len(bytes.TrimSpace(body)) == 0 {
		return nil, fmt.Errorf("%w: empty body", ErrInvalidResponse)
	}
	dec := json.NewDecoder(bytes.NewReader(body))
	var doc ResponseDoc
	if err := dec.Decode(&doc); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidResponse, err)
	}
	if err := dec.Decode(&struct{}{}); err != io.EOF {
		if err == nil {
			return nil, fmt.Errorf("%w: trailing data", ErrInvalidResponse)
		}
		return nil, fmt.Errorf("%w: %v", ErrInvalidResponse, err)
	}
	return &ChatResponse{
		raw: bytes.Clone(body),
		doc: doc,
	}, nil
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
	if c.forceBytesErr {
		return nil, fmt.Errorf("marshal chat response: %w", errors.New("forced"))
	}
	out, err := json.Marshal(c.doc)
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
		raw:   bytes.Clone(c.raw),
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
	return cp
}
