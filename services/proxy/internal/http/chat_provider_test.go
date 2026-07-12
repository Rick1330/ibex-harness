package http

import (
	"context"
	"errors"
	"net/http"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestMapProviderErr_providerError400(t *testing.T) {
	t.Parallel()
	code, status, detail, retry := mapProviderErr(&provider.ProviderError{
		StatusCode:     http.StatusBadRequest,
		ProviderErrMsg: "bad field",
	})
	if code != apierror.CodeInvalidRequest || status != http.StatusBadRequest || detail != "bad field" || retry != 0 {
		t.Fatalf("got code=%s status=%d detail=%q retry=%d", code, status, detail, retry)
	}
}

func TestMapProviderErr_providerError429(t *testing.T) {
	t.Parallel()
	code, status, _, retry := mapProviderErr(&provider.ProviderError{
		StatusCode: http.StatusTooManyRequests,
		RetryAfter: 30 * time.Second,
	})
	if code != apierror.CodeRateLimited || status != http.StatusTooManyRequests || retry != 30 {
		t.Fatalf("got code=%s status=%d retry=%d", code, status, retry)
	}
}

func TestMapProviderErr_providerError401(t *testing.T) {
	t.Parallel()
	code, status, detail, _ := mapProviderErr(&provider.ProviderError{StatusCode: http.StatusUnauthorized})
	if code != apierror.CodeProviderUnavailable || status != http.StatusServiceUnavailable || detail != msgProviderUnavailable {
		t.Fatalf("got code=%s status=%d detail=%q", code, status, detail)
	}
}

func TestMapProviderErr_timeout(t *testing.T) {
	t.Parallel()
	code, status, _, _ := mapProviderErr(context.DeadlineExceeded)
	if code != apierror.CodeProviderTimeout || status != http.StatusGatewayTimeout {
		t.Fatalf("got code=%s status=%d", code, status)
	}
}

func TestMapProviderErr_transport(t *testing.T) {
	t.Parallel()
	code, status, detail, _ := mapProviderErr(errors.New("dial tcp: connection refused"))
	if code != apierror.CodeProviderUnavailable || status != http.StatusServiceUnavailable || detail != msgProviderUnavailable {
		t.Fatalf("got code=%s status=%d detail=%q", code, status, detail)
	}
}

func TestProviderClientMessage_allCodes(t *testing.T) {
	t.Parallel()
	if providerClientMessage(apierror.CodeInvalidRequest) == "" {
		t.Fatal("expected message for invalid request")
	}
	if providerClientMessage(apierror.CodeRateLimited) == "" {
		t.Fatal("expected message for rate limited")
	}
}
