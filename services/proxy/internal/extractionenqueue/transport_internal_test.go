package extractionenqueue

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// fakeRoundTripper lets a test pass a non-*http.Transport base to newTransport.
type fakeRoundTripper struct{}

func (fakeRoundTripper) RoundTrip(*http.Request) (*http.Response, error) {
	return nil, errors.New("fakeRoundTripper: not used")
}

func TestUnit_NewClientUsesPrivateTransport(t *testing.T) {
	t.Parallel()
	c := New(Config{BaseURL: "http://127.0.0.1:9", Token: "t"})
	if !c.Enabled() {
		t.Fatal("expected enabled")
	}
	tr, ok := c.httpClient.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("transport type=%T want *http.Transport", c.httpClient.Transport)
	}
	// The identity check is the regression: a nil Transport on http.Client makes
	// Go use http.DefaultTransport, whose idle pool is process-global and can be
	// torn down by any caller of CloseIdleConnections (including another
	// test's httptest.Server.Close).
	if tr == http.DefaultTransport {
		t.Fatal("client shares http.DefaultTransport; idle pool is not private")
	}
	if tr.DisableKeepAlives {
		t.Fatal("keep-alives must stay enabled; the goal is a private pool, not no pool")
	}
	if tr.MaxIdleConns != maxIdleConns {
		t.Fatalf("MaxIdleConns=%d want %d", tr.MaxIdleConns, maxIdleConns)
	}
	if tr.MaxIdleConnsPerHost != maxIdleConnsPerHost {
		t.Fatalf("MaxIdleConnsPerHost=%d want %d", tr.MaxIdleConnsPerHost, maxIdleConnsPerHost)
	}
	if tr.IdleConnTimeout != idleConnTimeout {
		t.Fatalf("IdleConnTimeout=%s want %s", tr.IdleConnTimeout, idleConnTimeout)
	}
}

func TestUnit_NewTransportInheritsProcessDefaults(t *testing.T) {
	t.Parallel()
	base := http.DefaultTransport.(*http.Transport)
	tr, err := newTransport(base)
	if err != nil {
		t.Fatal(err)
	}
	// Cloning must carry the tuned defaults across, not build an empty transport.
	if tr.TLSHandshakeTimeout != base.TLSHandshakeTimeout {
		t.Fatalf("TLSHandshakeTimeout=%s want %s", tr.TLSHandshakeTimeout, base.TLSHandshakeTimeout)
	}
	if tr.ForceAttemptHTTP2 != base.ForceAttemptHTTP2 {
		t.Fatalf("ForceAttemptHTTP2=%v want %v", tr.ForceAttemptHTTP2, base.ForceAttemptHTTP2)
	}
	if tr.ResponseHeaderTimeout != base.ResponseHeaderTimeout {
		t.Fatalf("ResponseHeaderTimeout=%s want %s", tr.ResponseHeaderTimeout, base.ResponseHeaderTimeout)
	}
}

func TestUnit_NewTransportRejectsForeignBase(t *testing.T) {
	t.Parallel()
	tr, err := newTransport(fakeRoundTripper{})
	if err == nil {
		t.Fatal("expected an error for a non-*http.Transport base")
	}
	if tr != nil {
		t.Fatal("must not return a transport when it cannot clone the base")
	}
}

func TestUnit_EnqueueReportsTransportInitFailure(t *testing.T) {
	t.Parallel()
	boom := errors.New("transport unavailable")
	c := &Client{baseURL: "http://127.0.0.1:9", token: "t", initErr: boom}
	err := c.Enqueue(context.Background(), Request{
		Turns: []Turn{{TurnIndex: 0, Role: "user", Content: "hi"}},
	})
	if !errors.Is(err, boom) {
		t.Fatalf("err=%v want %v", err, boom)
	}
	if c.Enabled() {
		t.Fatal("a client without a transport must not report itself enabled")
	}
}

// TestUnit_NewClientRejectsUnclonableBase drives construction itself, not a
// hand-built Client: a base that is not an *http.Transport cannot be cloned, so
// newClient must keep the config for a precise Enqueue error and must not hold
// an http.Client with a nil transport, which would fall back to the shared
// process-global pool the private transport exists to avoid.
func TestUnit_NewClientRejectsUnclonableBase(t *testing.T) {
	t.Parallel()
	c := newClient(Config{BaseURL: "http://127.0.0.1:9", Token: "t"}, fakeRoundTripper{})
	if c.httpClient != nil {
		t.Fatalf("httpClient=%v want nil (nil transport would use http.DefaultTransport)", c.httpClient)
	}
	if c.Enabled() {
		t.Fatal("a client whose transport could not be built must not report itself enabled")
	}
	if c.initErr == nil {
		t.Fatal("expected the construction failure to be retained")
	}
	err := c.Enqueue(context.Background(), Request{
		OrgID: uuid.New(), AgentID: uuid.New(), SessionID: uuid.New(),
		Turns: []Turn{{TurnIndex: 0, Role: "user", Content: "hi"}},
	})
	if !errors.Is(err, c.initErr) {
		t.Fatalf("err=%v want the construction error %v", err, c.initErr)
	}
	if !strings.Contains(err.Error(), "base transport is") {
		t.Fatalf("err=%v should name the unclonable base transport", err)
	}
}
