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

type mapProviderErrCase struct {
	name       string
	err        error
	wantCode   apierror.Code
	wantStatus int
	wantDetail string
	wantRetry  int64
	wantOK     bool
}

func TestMapProviderErr(t *testing.T) {
	t.Parallel()

	cases := []mapProviderErrCase{
		{
			name: "provider 400",
			err: &provider.ProviderError{
				StatusCode:     http.StatusBadRequest,
				ProviderErrMsg: "bad field",
			},
			wantCode:   apierror.CodeInvalidRequest,
			wantStatus: http.StatusBadRequest,
			wantDetail: "bad field",
			wantOK:     true,
		},
		{
			name: "provider 429",
			err: &provider.ProviderError{
				StatusCode: http.StatusTooManyRequests,
				RetryAfter: 30 * time.Second,
			},
			wantCode:   apierror.CodeRateLimited,
			wantStatus: http.StatusTooManyRequests,
			wantRetry:  30,
			wantOK:     true,
		},
		{
			name:       "provider 401",
			err:        &provider.ProviderError{StatusCode: http.StatusUnauthorized},
			wantCode:   apierror.CodeProviderUnavailable,
			wantStatus: http.StatusServiceUnavailable,
			wantDetail: msgProviderUnavailable,
			wantOK:     true,
		},
		{
			name:       "timeout",
			err:        context.DeadlineExceeded,
			wantCode:   apierror.CodeProviderTimeout,
			wantStatus: http.StatusGatewayTimeout,
			wantOK:     true,
		},
		{
			name:   "canceled",
			err:    context.Canceled,
			wantOK: false,
		},
		{
			name:       "transport",
			err:        errors.New("dial tcp: connection refused"),
			wantCode:   apierror.CodeProviderUnavailable,
			wantStatus: http.StatusServiceUnavailable,
			wantDetail: msgProviderUnavailable,
			wantOK:     true,
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			assertMapProviderErr(t, tc)
		})
	}
}

func assertMapProviderErr(t *testing.T, tc mapProviderErrCase) {
	t.Helper()
	code, status, detail, retry, ok := mapProviderErr(tc.err)
	if ok != tc.wantOK {
		t.Fatalf("ok: got %v want %v", ok, tc.wantOK)
	}
	if !tc.wantOK {
		return
	}
	if code != tc.wantCode {
		t.Fatalf("code: got %s want %s", code, tc.wantCode)
	}
	if status != tc.wantStatus {
		t.Fatalf("status: got %d want %d", status, tc.wantStatus)
	}
	if tc.wantDetail != "" && detail != tc.wantDetail {
		t.Fatalf("detail: got %q want %q", detail, tc.wantDetail)
	}
	if retry != tc.wantRetry {
		t.Fatalf("retry: got %d want %d", retry, tc.wantRetry)
	}
}

func TestProviderClientMessage_allCodes(t *testing.T) {
	t.Parallel()
	for _, code := range []apierror.Code{
		apierror.CodeInvalidRequest,
		apierror.CodeRateLimited,
		apierror.CodeProviderTimeout,
		apierror.CodeProviderUnavailable,
	} {
		if providerClientMessage(code) == "" {
			t.Fatalf("expected message for %s", code)
		}
	}
}
