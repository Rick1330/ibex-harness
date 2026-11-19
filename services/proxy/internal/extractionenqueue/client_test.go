package extractionenqueue_test

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionenqueue"
	"github.com/google/uuid"
)

// claimParts splits a signed claim and checks the v1 shape every enqueue sends,
// returning the six signing fields plus the signature for per-field assertions.
func claimParts(t *testing.T, claim string) []string {
	t.Helper()
	parts := strings.Split(claim, ":")
	if len(parts) != 7 {
		t.Fatalf("claim=%q parts=%d want 7", claim, len(parts))
	}
	if parts[0] != "v1" {
		t.Fatalf("version=%q want v1", parts[0])
	}
	return parts
}

// assertClaimIDs checks the org, agent, and session fields name want, one field
// at a time so a failure says which id drifted.
func assertClaimIDs(t *testing.T, parts []string, want [3]uuid.UUID) {
	t.Helper()
	names := [...]string{"org", "agent", "session"}
	for i, name := range names {
		if parts[i+1] != want[i].String() {
			t.Fatalf("%s id=%q want %s", name, parts[i+1], want[i])
		}
	}
}

// assertClaimBinds checks the claim names the org, agent, and session from req.
func assertClaimBinds(t *testing.T, claim extractionenqueue.Claim, req extractionenqueue.Request) {
	t.Helper()
	if claim.OrgID != req.OrgID {
		t.Fatalf("claim org=%s want %s", claim.OrgID, req.OrgID)
	}
	if claim.AgentID != req.AgentID {
		t.Fatalf("claim agent=%s want %s", claim.AgentID, req.AgentID)
	}
	if claim.SessionID != req.SessionID {
		t.Fatalf("claim session=%s want %s", claim.SessionID, req.SessionID)
	}
}

// assertClaimMAC recomputes the HMAC over the six signing fields and compares it
// with the signature field, so a claim that signs the wrong bytes fails.
func assertClaimMAC(t *testing.T, parts []string, secret string) {
	t.Helper()
	want := hmac.New(sha256.New, []byte(secret))
	_, _ = want.Write([]byte(strings.Join(parts[:6], ":")))
	if !hmac.Equal([]byte(parts[6]), []byte(hex.EncodeToString(want.Sum(nil)))) {
		t.Fatal("mac does not cover the claimed fields")
	}
}

func TestUnit_ClientDisabled(t *testing.T) {
	t.Parallel()
	c := extractionenqueue.New(extractionenqueue.Config{})
	if c.Enabled() {
		t.Fatal("expected disabled")
	}
}

func TestUnit_ClientEnqueueOK(t *testing.T) {
	t.Parallel()
	var gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		if r.URL.Path != "/internal/extraction/enqueue" {
			t.Fatalf("path=%s", r.URL.Path)
		}
		body, _ := io.ReadAll(r.Body)
		if len(body) == 0 {
			t.Fatal("empty body")
		}
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte(`{"task_id":"t1"}`))
	}))
	t.Cleanup(srv.Close)

	c := extractionenqueue.New(extractionenqueue.Config{
		BaseURL: srv.URL, Token: "sekrit", Timeout: time.Second,
	})
	err := c.Enqueue(context.Background(), extractionenqueue.Request{
		OrgID: uuid.New(), AgentID: uuid.New(), SessionID: uuid.New(),
		Turns: []extractionenqueue.Turn{{TurnIndex: 0, Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if gotAuth != "Bearer sekrit" {
		t.Fatalf("auth=%q", gotAuth)
	}
}

func TestUnit_ClientEnqueueNonAccepted2xx(t *testing.T) {
	t.Parallel()
	for _, code := range []int{http.StatusOK, http.StatusNoContent} {
		code := code
		t.Run(http.StatusText(code), func(t *testing.T) {
			t.Parallel()
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(code)
			}))
			t.Cleanup(srv.Close)
			c := extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "t"})
			err := c.Enqueue(context.Background(), extractionenqueue.Request{
				OrgID: uuid.New(), AgentID: uuid.New(), SessionID: uuid.New(),
				Turns: []extractionenqueue.Turn{{TurnIndex: 0, Role: "user", Content: "hi"}},
			})
			if err == nil {
				t.Fatalf("status %d must be treated as failure", code)
			}
		})
	}
}

func TestUnit_ClientEnqueueHTTPError(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	t.Cleanup(srv.Close)
	c := extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "t"})
	err := c.Enqueue(context.Background(), extractionenqueue.Request{
		OrgID: uuid.New(), AgentID: uuid.New(), SessionID: uuid.New(),
		Turns: []extractionenqueue.Turn{{TurnIndex: 0, Role: "user", Content: "hi"}},
	})
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_ClientEnqueueIdempotencyKey(t *testing.T) {
	t.Parallel()
	sid := uuid.New()
	var gotKey string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotKey = r.Header.Get("Idempotency-Key")
		w.WriteHeader(http.StatusAccepted)
	}))
	t.Cleanup(srv.Close)
	c := extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "t"})
	if err := c.Enqueue(context.Background(), extractionenqueue.Request{
		OrgID: uuid.New(), AgentID: uuid.New(), SessionID: sid,
		Turns: []extractionenqueue.Turn{{TurnIndex: 0, Role: "user", Content: "hi"}},
	}); err != nil {
		t.Fatal(err)
	}
	if gotKey != sid.String() {
		t.Fatalf("Idempotency-Key=%q want %s", gotKey, sid)
	}
}

func TestUnit_ClientEnqueueGuards(t *testing.T) {
	t.Parallel()
	c := extractionenqueue.New(extractionenqueue.Config{})
	if err := c.Enqueue(context.Background(), extractionenqueue.Request{
		Turns: []extractionenqueue.Turn{{TurnIndex: 0, Role: "user", Content: "hi"}},
	}); err == nil {
		t.Fatal("expected disabled error")
	}
	ok := extractionenqueue.New(extractionenqueue.Config{BaseURL: "http://127.0.0.1:9", Token: "t"})
	if err := ok.Enqueue(context.Background(), extractionenqueue.Request{
		OrgID: uuid.New(), AgentID: uuid.New(), SessionID: uuid.New(),
	}); err == nil {
		t.Fatal("expected turns required")
	}
}

func TestUnit_ClientDefaultTimeout(t *testing.T) {
	t.Parallel()
	c := extractionenqueue.New(extractionenqueue.Config{BaseURL: "http://example.invalid", Token: "t", Timeout: 0})
	if !c.Enabled() {
		t.Fatal("expected enabled")
	}
}

func TestUnit_ClaimSignsExpectedFieldsAndIsStable(t *testing.T) {
	t.Parallel()
	org, agent, sid := uuid.MustParse("11111111-1111-1111-1111-111111111111"),
		uuid.MustParse("22222222-2222-2222-2222-222222222222"),
		uuid.MustParse("33333333-3333-3333-3333-333333333333")
	exp := time.Unix(1_800_000_000, 0).UTC()
	claim := extractionenqueue.Claim{
		OrgID: org, AgentID: agent, SessionID: sid, JTI: "jti-fixed", ExpiresAt: exp,
	}

	first, err := claim.Sign("sekrit")
	if err != nil {
		t.Fatal(err)
	}
	second, err := claim.Sign("sekrit")
	if err != nil {
		t.Fatal(err)
	}
	if first != second {
		t.Fatalf("claim not stable:\n%s\n%s", first, second)
	}

	parts := claimParts(t, first)
	assertClaimIDs(t, parts, [3]uuid.UUID{org, agent, sid})
	if parts[4] != "jti-fixed" {
		t.Fatalf("jti=%q", parts[4])
	}
	if parts[5] != "1800000000" {
		t.Fatalf("exp=%q", parts[5])
	}
	assertClaimMAC(t, parts, "sekrit")
}

func TestUnit_ClaimRejectsMissingParts(t *testing.T) {
	t.Parallel()
	if _, err := (extractionenqueue.Claim{}).Sign("sekrit"); err == nil {
		t.Fatal("expected error for empty claim")
	}
	full := extractionenqueue.Claim{
		OrgID: uuid.New(), AgentID: uuid.New(), SessionID: uuid.New(), JTI: "j",
		ExpiresAt: time.Now().Add(time.Minute),
	}
	if _, err := full.Sign(""); err == nil {
		t.Fatal("expected error for empty secret")
	}
}

func TestUnit_NewClaimUsesRequestIDsAndBoundedExpiry(t *testing.T) {
	t.Parallel()
	now := time.Unix(1_800_000_000, 750*int64(time.Millisecond))
	req := extractionenqueue.Request{OrgID: uuid.New(), AgentID: uuid.New(), SessionID: uuid.New()}
	claim := extractionenqueue.NewClaim(req, now)
	assertClaimBinds(t, claim, req)
	if claim.JTI == "" {
		t.Fatal("jti required")
	}
	wantExp := now.Add(extractionenqueue.ClaimTTL).UTC().Truncate(time.Second)
	if !claim.ExpiresAt.Equal(wantExp) {
		t.Fatalf("exp=%s want %s", claim.ExpiresAt, wantExp)
	}
	other := extractionenqueue.NewClaim(req, now)
	if other.JTI == claim.JTI {
		t.Fatal("each claim must carry a fresh jti")
	}
}

func TestUnit_ClientSendsClaimHeader(t *testing.T) {
	t.Parallel()
	org, agent, sid := uuid.New(), uuid.New(), uuid.New()
	var gotClaim string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotClaim = r.Header.Get(extractionenqueue.ClaimHeader)
		w.WriteHeader(http.StatusAccepted)
	}))
	t.Cleanup(srv.Close)
	c := extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "sekrit"})
	err := c.Enqueue(context.Background(), extractionenqueue.Request{
		OrgID: org, AgentID: agent, SessionID: sid,
		Turns: []extractionenqueue.Turn{{TurnIndex: 0, Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	parts := claimParts(t, gotClaim)
	assertClaimIDs(t, parts, [3]uuid.UUID{org, agent, sid})
	exp, err := strconv.ParseInt(parts[5], 10, 64)
	if err != nil {
		t.Fatalf("exp=%q: %v", parts[5], err)
	}
	if exp <= time.Now().Unix() {
		t.Fatalf("exp=%d is not in the future", exp)
	}
	if exp > time.Now().Add(extractionenqueue.ClaimTTL+time.Second).Unix() {
		t.Fatalf("exp=%d is past the claim window", exp)
	}
	assertClaimMAC(t, parts, "sekrit")
}

func TestUnit_ClientSignsEveryEnqueue(t *testing.T) {
	t.Parallel()
	claims := make(chan string, 2)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		claims <- r.Header.Get(extractionenqueue.ClaimHeader)
		w.WriteHeader(http.StatusAccepted)
	}))
	t.Cleanup(srv.Close)
	c := extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "sekrit"})
	req := extractionenqueue.Request{
		OrgID: uuid.New(), AgentID: uuid.New(), SessionID: uuid.New(),
		Turns: []extractionenqueue.Turn{{TurnIndex: 0, Role: "user", Content: "hi"}},
	}
	for range 2 {
		if err := c.Enqueue(context.Background(), req); err != nil {
			t.Fatal(err)
		}
	}
	first, second := <-claims, <-claims
	if first == second {
		t.Fatal("each enqueue must carry a distinct claim (fresh jti)")
	}
}

func TestUnit_ClientNilSessionFailsBeforeHTTP(t *testing.T) {
	t.Parallel()
	// A nil session id cannot be bound to a claim; the client fails closed on the
	// enqueue attempt, which the handler treats as fail-open (buffer retained).
	hits := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		hits++
		w.WriteHeader(http.StatusAccepted)
	}))
	t.Cleanup(srv.Close)
	c := extractionenqueue.New(extractionenqueue.Config{BaseURL: srv.URL, Token: "sekrit"})
	err := c.Enqueue(context.Background(), extractionenqueue.Request{
		OrgID: uuid.New(), AgentID: uuid.New(),
		Turns: []extractionenqueue.Turn{{TurnIndex: 0, Role: "user", Content: "hi"}},
	})
	if err == nil {
		t.Fatal("expected error for nil session id")
	}
	if hits != 0 {
		t.Fatalf("hits=%d want 0", hits)
	}
}

// newConnCountingServer starts an httptest server that counts accepted
// connections. A reused keep-alive connection does not change the count, so the
// counter distinguishes "the idle pool still holds my conn" from "I had to
// redial".
func newConnCountingServer(t *testing.T) (*httptest.Server, *atomic.Int64) {
	t.Helper()
	srv := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusAccepted)
	}))
	var accepted atomic.Int64
	srv.Config.ConnState = func(_ net.Conn, state http.ConnState) {
		if state == http.StateNew {
			accepted.Add(1)
		}
	}
	srv.Start()
	return srv, &accepted
}

// warmUntilReused enqueues until a request completes without opening a new
// connection, proving the transport's idle pool holds the conn. It bounds the
// attempts so a keep-alive regression fails the test instead of hanging.
func warmUntilReused(t *testing.T, c *extractionenqueue.Client, req extractionenqueue.Request, accepted *atomic.Int64) bool {
	t.Helper()
	for range 50 {
		before := accepted.Load()
		if err := c.Enqueue(context.Background(), req); err != nil {
			t.Fatal(err)
		}
		if accepted.Load() == before {
			return true
		}
	}
	return false
}

// assertPoolWarm proves the client holds a pooled connection to the victim and
// returns the accept count that establishes the baseline. It fails the test when
// the client never reuses a connection, because a foreign pool close could then
// not be detected at all.
func assertPoolWarm(t *testing.T, c *extractionenqueue.Client, req extractionenqueue.Request, accepted *atomic.Int64) int64 {
	t.Helper()
	if err := c.Enqueue(context.Background(), req); err != nil {
		t.Fatal(err)
	}
	if !warmUntilReused(t, c, req, accepted) {
		t.Fatal("client never reused a pooled connection; cannot detect a foreign pool close")
	}
	return accepted.Load()
}

// startVictimHammer enqueues continuously until the returned stop function is
// called. Errors are counted instead of failing: the zero-error assertion
// belongs to the caller. The goroutine can only be released through stop, which
// waits for it to exit, so no caller can leak it.
func startVictimHammer(c *extractionenqueue.Client, req extractionenqueue.Request) (*atomic.Int64, func()) {
	var errs atomic.Int64
	stop := make(chan struct{})
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		for {
			select {
			case <-stop:
				return
			default:
			}
			if err := c.Enqueue(context.Background(), req); err != nil {
				errs.Add(1)
			}
			time.Sleep(time.Millisecond)
		}
	}()
	return &errs, func() {
		close(stop)
		wg.Wait()
	}
}

// closeServersConcurrently closes every server at once, so all their
// CloseIdleConnections calls land while the victim is still enqueueing.
func closeServersConcurrently(servers []*httptest.Server) {
	var wg sync.WaitGroup
	for _, srv := range servers {
		wg.Add(1)
		go func(s *httptest.Server) {
			defer wg.Done()
			s.Close()
		}(srv)
	}
	wg.Wait()
}

// TestUnit_ClientPoolIsPrivate is the regression test for the shared-pool
// defect. Every httptest.Server.Close closes idle connections on
// http.DefaultTransport. A client with a nil Transport inherits that global
// pool, so closing an unrelated server tears down this client's idle conn and
// forces a redial (and, rarely, breaks an in-flight request). A private
// transport must be immune.
func TestUnit_ClientPoolIsPrivate(t *testing.T) {
	t.Parallel()
	victim, accepted := newConnCountingServer(t)
	t.Cleanup(victim.Close)
	c := extractionenqueue.New(extractionenqueue.Config{BaseURL: victim.URL, Token: "t"})
	req := extractionenqueue.Request{
		OrgID: uuid.New(), AgentID: uuid.New(), SessionID: uuid.New(),
		Turns: []extractionenqueue.Turn{{TurnIndex: 0, Role: "user", Content: "hi"}},
	}

	warmAccepts := assertPoolWarm(t, c, req, accepted)

	// Unrelated servers, closed concurrently while the victim keeps enqueueing.
	// With a shared transport each Close closes the victim's idle conn.
	const closeCount = 16
	others := make([]*httptest.Server, closeCount)
	for i := range others {
		others[i], _ = newConnCountingServer(t)
		t.Cleanup(others[i].Close)
	}

	victimErrs, stopVictim := startVictimHammer(c, req)
	closeServersConcurrently(others)
	// Stop the hammer before the check below: nothing may enqueue concurrently
	// with the request whose connection outcome this test measures.
	stopVictim()

	if n := victimErrs.Load(); n != 0 {
		t.Fatalf("victim enqueue errors=%d want 0", n)
	}
	// Exactly one request after the storm, from this goroutine, so a redial
	// forced by a foreign pool close is counted. Waiting for the hammer to
	// happen to issue one would make the accept count depend on scheduling.
	if err := c.Enqueue(context.Background(), req); err != nil {
		t.Fatalf("post-storm enqueue: %v", err)
	}
	if got := accepted.Load(); got != warmAccepts {
		t.Fatalf("victim accepted=%d want %d: closing unrelated servers disturbed its idle pool", got, warmAccepts)
	}
}
