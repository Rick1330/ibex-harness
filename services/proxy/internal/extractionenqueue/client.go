// Package extractionenqueue is a fail-open HTTP client for worker extraction enqueue.
//
// Every request carries a signed tenant claim (ClaimHeader) alongside the static
// bearer, so the worker can prove which tenant the proxy authenticated instead of
// trusting the org_id in the body. The client stays fail-open: an enqueue failure,
// including a claim-signing failure, is returned as an error for metrics and
// logging only and never fails the caller's request.
//
// Known limit: the signing key is the same secret as the bearer, so a leaked
// bearer can still forge a claim. The claim's value is that the tenant is no
// longer an unsigned body field and is bound to the agent, session, and a short
// expiry. A separate claim secret would make it a second factor; that is a config
// change, not a contract change.
package extractionenqueue

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

const (
	// DefaultTimeout bounds the internal enqueue HTTP call.
	DefaultTimeout = 2 * time.Second
	enqueuePath    = "/internal/extraction/enqueue"

	// Idle-pool bounds for this client's private transport. Config.BaseURL is a
	// single worker host, so these are per-host numbers, not a fleet budget.
	//
	// MaxIdleConnsPerHost: http.DefaultTransport keeps only 2 idle conns per
	// host. A burst of concurrent session terminations therefore tears down the
	// extra conns and re-dials them on the next burst. 10 covers normal enqueue
	// fan-out while keeping the fd cost of an idle proxy small.
	maxIdleConnsPerHost = 10
	// MaxIdleConns: with one host the per-host cap already bounds the pool, so
	// the process-wide cap is set equal to make the single-host assumption
	// explicit and to keep the total bounded if BaseURL ever spans hosts.
	maxIdleConns = 10
	// IdleConnTimeout: below the 90s default, and a deliberate backstop rather
	// than the primary eviction path. The worker is uvicorn with its default
	// timeout_keep_alive of 5s (services/worker/app/enqueue_http.py), so the
	// server normally closes an idle conn long before this fires and the
	// transport's readLoop drops it on FIN. 30s bounds the case where the server
	// does not close (a proxy or NAT holding the path), so a dead socket cannot
	// sit in the pool for a minute and a half.
	idleConnTimeout = 30 * time.Second

	// ClaimHeader carries the tenant claim that binds the body to the tenant the
	// proxy already authenticated (S01). The static bearer stays transport auth;
	// the claim is what authorizes *which* tenant the worker acts for.
	ClaimHeader = "x-ibex-claim"

	// ClaimTTL bounds how long a minted claim is accepted by the worker.
	ClaimTTL = 60 * time.Second

	claimVersion = "v1"
)

// Claim is the tenant binding for one enqueue request. It is signed with the
// shared enqueue secret, so the worker can reject a body that names a different
// org, agent, or session than the one the proxy validated.
type Claim struct {
	OrgID     uuid.UUID
	AgentID   uuid.UUID
	SessionID uuid.UUID
	// JTI identifies this claim. It is not stored by the worker: replay is
	// bounded by ClaimTTL, and a replayed claim can only re-assert the same
	// (org, agent, session) tuple, which the worker already dedupes by
	// Idempotency-Key.
	JTI       string
	ExpiresAt time.Time
}

// NewClaim builds a claim for req, valid for ClaimTTL from now. JTI is unique per
// call; the signing itself is a pure function of the claim, so the same claim
// always produces the same header value.
func NewClaim(req Request, now time.Time) Claim {
	return Claim{
		OrgID:     req.OrgID,
		AgentID:   req.AgentID,
		SessionID: req.SessionID,
		JTI:       uuid.NewString(),
		ExpiresAt: now.Add(ClaimTTL).UTC().Truncate(time.Second),
	}
}

// signingString is the canonical string the MAC covers. The worker rebuilds this
// exact shape, so any change here is a cross-language contract change.
//
//	v1:<org_id>:<agent_id>:<session_id>:<jti>:<exp_unix_seconds>
func (c Claim) signingString() string {
	return strings.Join([]string{
		claimVersion,
		c.OrgID.String(),
		c.AgentID.String(),
		c.SessionID.String(),
		c.JTI,
		strconv.FormatInt(c.ExpiresAt.Unix(), 10),
	}, ":")
}

// Sign returns the x-ibex-claim header value: the signing string plus the
// lowercase hex HMAC-SHA256 of that string under secret.
func (c Claim) Sign(secret string) (string, error) {
	if secret == "" {
		return "", fmt.Errorf("extractionenqueue: claim secret required")
	}
	if c.JTI == "" {
		return "", fmt.Errorf("extractionenqueue: claim jti required")
	}
	if !c.hasIDs() {
		return "", fmt.Errorf("extractionenqueue: claim ids required")
	}
	payload := c.signingString()
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(payload))
	return payload + ":" + hex.EncodeToString(mac.Sum(nil)), nil
}

// hasIDs reports whether the claim names a tenant, an agent, and a session. A
// claim missing any of them cannot be scoped by the worker, so Sign refuses it.
func (c Claim) hasIDs() bool {
	for _, id := range [...]uuid.UUID{c.OrgID, c.AgentID, c.SessionID} {
		if id == uuid.Nil {
			return false
		}
	}
	return true
}

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
	// initErr records a transport that could not be constructed. It is immutable
	// after New, so it needs no synchronization.
	initErr error
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
	tr, err := newTransport(http.DefaultTransport)
	if err != nil {
		// Do not fall back to http.DefaultTransport: sharing the process-global
		// pool is the defect this client avoids. Keep the config so Enqueue can
		// report the precise cause instead of a generic "disabled".
		return &Client{baseURL: base, token: token, initErr: err}
	}
	return &Client{
		baseURL: base,
		token:   token,
		httpClient: &http.Client{
			Timeout:   to,
			Transport: tr,
		},
	}
}

// newTransport builds the client's private connection pool. It clones base so
// the process's tuned defaults (dial timeout, TLS handshake timeout, proxy,
// HTTP/2) are inherited, then bounds the idle pool for a single-host internal
// client. It never returns base itself: http.DefaultTransport is shared with
// every other net/http user in the process, so any caller of
// CloseIdleConnections (httptest.Server.Close does exactly that) would tear
// down idle connections this client owns.
func newTransport(base http.RoundTripper) (*http.Transport, error) {
	dt, ok := base.(*http.Transport)
	if !ok {
		return nil, fmt.Errorf("extractionenqueue: base transport is %T, want *http.Transport", base)
	}
	tr := dt.Clone()
	tr.MaxIdleConns = maxIdleConns
	tr.MaxIdleConnsPerHost = maxIdleConnsPerHost
	tr.IdleConnTimeout = idleConnTimeout
	return tr, nil
}

// configured reports whether the client has the base URL and token an enqueue
// needs. It is separate from Enabled so a client whose transport could not be
// built still reports a precise error instead of the generic disabled one.
func (c *Client) configured() bool {
	if c == nil {
		return false
	}
	if c.baseURL == "" {
		return false
	}
	return c.token != ""
}

// Enabled reports whether enqueue calls will be attempted.
func (c *Client) Enabled() bool {
	return c.configured() && c.httpClient != nil
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
	claim, err := NewClaim(req, time.Now()).Sign(c.token)
	if err != nil {
		return nil, err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+enqueuePath, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("extractionenqueue: request: %w", err)
	}
	setEnqueueHeaders(httpReq, c.token, req.SessionID, claim)
	return httpReq, nil
}

func (c *Client) validateEnqueue(req Request) error {
	if !c.configured() {
		return fmt.Errorf("extractionenqueue: disabled")
	}
	if c.initErr != nil {
		return c.initErr
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

func setEnqueueHeaders(httpReq *http.Request, token string, sessionID uuid.UUID, claim string) {
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+token)
	httpReq.Header.Set(ClaimHeader, claim)
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
	if code == http.StatusAccepted {
		return nil
	}
	return fmt.Errorf("extractionenqueue: status %d", code)
}
