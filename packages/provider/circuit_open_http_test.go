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
	br, err := circuitbreaker.New(circuitbreaker.Settings{
		Name: "pe-4xx", MaxFailures: 2, CoolDown: time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	bad := &provider.ProviderError{ProviderName: "openai", StatusCode: http.StatusBadRequest, ProviderErrMsg: "bad"}
	for i := 0; i < 5; i++ {
		_, err := br.Execute(func() (any, error) {
			return nil, provider.ClassifyForBreaker(t.Context(), bad)
		})
		if !errors.As(err, new(*provider.ProviderError)) {
			t.Fatalf("i=%d err=%v", i, err)
		}
	}
	if br.State() != "closed" {
		t.Fatalf("state=%s after 4xx burst", br.State())
	}

	br5, err := circuitbreaker.New(circuitbreaker.Settings{
		Name: "pe-5xx", MaxFailures: 2, CoolDown: time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	boom := &provider.ProviderError{ProviderName: "openai", StatusCode: http.StatusInternalServerError, ProviderErrMsg: "boom"}
	_, _ = br5.Execute(func() (any, error) { return nil, boom })
	_, _ = br5.Execute(func() (any, error) { return nil, boom })
	if br5.State() != "open" {
		t.Fatalf("state=%s want open after 5xx", br5.State())
	}
}
