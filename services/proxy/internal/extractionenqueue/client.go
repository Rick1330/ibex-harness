// Package extractionenqueue is a fail-open HTTP client for worker extraction enqueue.
package extractionenqueue

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
)

const (
	// DefaultTimeout bounds the internal enqueue HTTP call.
	DefaultTimeout = 2 * time.Second
	enqueuePath    = "/internal/extraction/enqueue"
)

// Turn mirrors the worker TurnPayload JSON shape.
type Turn struct {
	TurnIndex int    `json:"turn_index"`
	Role      string `json:"role"`
	Content   string `json:"content"`
}

// Request is the body for POST /internal/extraction/enqueue.
type Request struct {
	OrgID     uuid.UUID `json:"org_id"`
	AgentID   uuid.UUID `json:"agent_id"`
	SessionID uuid.UUID `json:"session_id"`
	Turns     []Turn    `json:"turns"`
}

// Client posts enqueue requests to the worker Starlette surface.
type Client struct {
	baseURL    string
	token      string
	httpClient *http.Client
}

// Config wires the enqueue client.
type Config struct {
	BaseURL string
	Token   string
	Timeout time.Duration
}

// New returns a Client. Empty BaseURL or Token means the client is disabled.
func New(cfg Config) *Client {
	base := strings.TrimRight(strings.TrimSpace(cfg.BaseURL), "/")
	token := strings.TrimSpace(cfg.Token)
	if base == "" || token == "" {
		return &Client{}
	}
	to := cfg.Timeout
	if to <= 0 {
		to = DefaultTimeout
	}
	return &Client{
		baseURL: base,
		token:   token,
		httpClient: &http.Client{
			Timeout: to,
		},
	}
}

// Enabled reports whether enqueue calls will be attempted.
func (c *Client) Enabled() bool {
	return c != nil && c.baseURL != "" && c.token != "" && c.httpClient != nil
}

// Enqueue posts the task; errors are for metrics/logging only (fail-open).
func (c *Client) Enqueue(ctx context.Context, req Request) error {
	httpReq, err := c.newEnqueueHTTPRequest(ctx, req)
	if err != nil {
		return err
	}
	return c.doEnqueue(httpReq)
}

func (c *Client) newEnqueueHTTPRequest(ctx context.Context, req Request) (*http.Request, error) {
	if err := c.validateEnqueue(req); err != nil {
		return nil, err
	}
	body, err := marshalEnqueue(req)
	if err != nil {
		return nil, err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+enqueuePath, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("extractionenqueue: request: %w", err)
	}
	setEnqueueHeaders(httpReq, c.token, req.SessionID)
	return httpReq, nil
}

func (c *Client) validateEnqueue(req Request) error {
	if !c.Enabled() {
		return fmt.Errorf("extractionenqueue: disabled")
	}
	if len(req.Turns) == 0 {
		return fmt.Errorf("extractionenqueue: turns required")
	}
	return nil
}

func marshalEnqueue(req Request) ([]byte, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("extractionenqueue: marshal: %w", err)
	}
	return body, nil
}

func setEnqueueHeaders(httpReq *http.Request, token string, sessionID uuid.UUID) {
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+token)
	if sessionID == uuid.Nil {
		return
	}
	httpReq.Header.Set("Idempotency-Key", sessionID.String())
}

func (c *Client) doEnqueue(httpReq *http.Request) error {
	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("extractionenqueue: do: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()
	_, _ = io.Copy(io.Discard, resp.Body)
	return enqueueStatusErr(resp.StatusCode)
}

func enqueueStatusErr(code int) error {
	if code >= 200 && code < 300 {
		return nil
	}
	return fmt.Errorf("extractionenqueue: status %d", code)
}
