package extractionenqueue_test

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionenqueue"
	"github.com/google/uuid"
)

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
