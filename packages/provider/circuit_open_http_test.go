package provider_test

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/circuitbreaker"
	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestCircuitOpen_WriteHTTPSetsRetryAfter(t *testing.T) {
	t.Parallel()
	cool := 30 * time.Second
	mapped := mapOpenBreaker(t, cool)
	assertWriteHTTPCircuitOpen(t, mapped, cool)
}

func mapOpenBreaker(t *testing.T, cool time.Duration) *apierror.Error {
	t.Helper()
	br, err := circuitbreaker.New(circuitbreaker.Settings{
		Name: "http-ra", MaxFailures: 1, CoolDown: cool,
	})
	if err != nil {
		t.Fatal(err)
	}
	_, _ = br.Execute(func() (any, error) { return nil, errors.New("upstream") })
	_, openErr := br.Execute(func() (any, error) { return "ok", nil })
	_, mapErr := provider.MapBreakerError("openai", openErr)
	mapped, write := provider.MapError(mapErr)
	if !write || mapped == nil {
		t.Fatalf("mapped=%v write=%v", mapped, write)
	}
	if mapped.HTTPStatus != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", mapped.HTTPStatus)
	}
	if mapped.RetryAfter != cool {
		t.Fatalf("RetryAfter=%v want %v", mapped.RetryAfter, cool)
	}
	return mapped
}

func assertWriteHTTPCircuitOpen(t *testing.T, mapped *apierror.Error, cool time.Duration) {
	t.Helper()
	rec := httptest.NewRecorder()
	apierror.WriteHTTP(rec, "req-cb", apierror.WriteOpts{}, mapped)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("HTTP status=%d", rec.Code)
	}
	wantRA := strconv.FormatInt(int64(cool/time.Second), 10)
	if got := rec.Header().Get("Retry-After"); got != wantRA {
		t.Fatalf("Retry-After=%q want %q", got, wantRA)
	}
	var body apierror.Response
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Error.Code != apierror.CodeProviderUnavailable {
		t.Fatalf("code=%s", body.Error.Code)
	}
}

func TestBreaker_ProviderError4xxDoesNotTrip_500Does(t *testing.T) {
	t.Parallel()
	assertProviderStatusLeavesClosed(t, http.StatusBadRequest, 5)
	assertProviderStatusOpens(t, http.StatusInternalServerError, 2)
}

func assertProviderStatusLeavesClosed(t *testing.T, status int, n int) {
	t.Helper()
	br := newNamedBreaker(t, "pe-closed", 2)
	pe := &provider.ProviderError{ProviderName: "openai", StatusCode: status, ProviderErrMsg: "x"}
	for i := 0; i < n; i++ {
		_, err := br.Execute(func() (any, error) {
			return nil, provider.ClassifyForBreaker(t.Context(), pe)
		})
		if !errors.As(err, new(*provider.ProviderError)) {
			t.Fatalf("i=%d err=%v", i, err)
		}
	}
	if br.State() != "closed" {
		t.Fatalf("state=%s after status=%d burst", br.State(), status)
	}
}

func assertProviderStatusOpens(t *testing.T, status, failures int) {
	t.Helper()
	br := newNamedBreaker(t, "pe-open", uint32(failures))
	pe := &provider.ProviderError{ProviderName: "openai", StatusCode: status, ProviderErrMsg: "x"}
	for i := 0; i < failures; i++ {
		_, _ = br.Execute(func() (any, error) { return nil, pe })
	}
	if br.State() != "open" {
		t.Fatalf("state=%s want open after status=%d", br.State(), status)
	}
}

func newNamedBreaker(t *testing.T, name string, maxFailures uint32) *circuitbreaker.Breaker {
	t.Helper()
	br, err := circuitbreaker.New(circuitbreaker.Settings{
		Name: name, MaxFailures: maxFailures, CoolDown: time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	return br
}
