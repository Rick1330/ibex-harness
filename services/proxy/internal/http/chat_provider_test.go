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

func TestMapProviderErr(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name       string
		err        error
		wantCode   apierror.Code
		wantStatus int
		wantDetail string
		wantRetry  int64
	}{
		{
			name: "provider 400",
			err: &provider.ProviderError{
				StatusCode:     http.StatusBadRequest,
				ProviderErrMsg: "bad field",
			},
			wantCode:   apierror.CodeInvalidRequest,
			wantStatus: http.StatusBadRequest,
			wantDetail: "bad field",
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
		},
		{
			name:       "provider 401",
			err:        &provider.ProviderError{StatusCode: http.StatusUnauthorized},
			wantCode:   apierror.CodeProviderUnavailable,
			wantStatus: http.StatusServiceUnavailable,
			wantDetail: msgProviderUnavailable,
		},
		{
			name:       "timeout",
			err:        context.DeadlineExceeded,
			wantCode:   apierror.CodeProviderTimeout,
			wantStatus: http.StatusGatewayTimeout,
		},
		{
			name:       "transport",
			err:        errors.New("dial tcp: connection refused"),
			wantCode:   apierror.CodeProviderUnavailable,
			wantStatus: http.StatusServiceUnavailable,
			wantDetail: msgProviderUnavailable,
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			code, status, detail, retry := mapProviderErr(tc.err)
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
		})
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
