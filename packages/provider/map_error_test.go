package provider

import (
	"context"
	"errors"
	"net/http"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
)

type mapCase struct {
	name       string
	in         MapInput
	wantNil    bool
	wantCode   apierror.Code
	wantStatus int
	wantRetry  time.Duration
}

// Case data lives outside test funcs so CodeScene does not count them as method size.
var mapProviderCoreCases = []mapCase{
	{
		name: "OpenAI429",
		in: MapInput{
			ProviderName: "openai",
			StatusCode:   http.StatusTooManyRequests,
			RetryAfter:   30 * time.Second,
		},
		wantCode:   apierror.CodeRateLimited,
		wantStatus: http.StatusTooManyRequests,
		wantRetry:  30 * time.Second,
	},
	{
		name:       "OpenAI401",
		in:         MapInput{ProviderName: "openai", StatusCode: http.StatusUnauthorized},
		wantCode:   apierror.CodeProviderUnavailable,
		wantStatus: http.StatusServiceUnavailable,
	},
	{
		name:       "Timeout",
		in:         MapInput{TransportErr: context.DeadlineExceeded},
		wantCode:   apierror.CodeProviderTimeout,
		wantStatus: http.StatusGatewayTimeout,
	},
	{
		name:       "400",
		in:         MapInput{StatusCode: 400, SafeMessage: "missing messages"},
		wantCode:   apierror.CodeInvalidRequest,
		wantStatus: 400,
	},
	{
		name:       "403",
		in:         MapInput{StatusCode: 403},
		wantCode:   apierror.CodeProviderUnavailable,
		wantStatus: 503,
	},
	{
		name:       "404",
		in:         MapInput{StatusCode: 404},
		wantCode:   apierror.CodeProviderUnavailable,
		wantStatus: 503,
	},
}

var mapProviderServerCases = []mapCase{
	{name: "500", in: MapInput{StatusCode: 500}, wantCode: apierror.CodeProviderUnavailable, wantStatus: 503},
	{name: "502", in: MapInput{StatusCode: 502}, wantCode: apierror.CodeProviderUnavailable, wantStatus: 503},
	{name: "503", in: MapInput{StatusCode: 503}, wantCode: apierror.CodeProviderUnavailable, wantStatus: 503},
	{name: "504", in: MapInput{StatusCode: 504}, wantCode: apierror.CodeProviderUnavailable, wantStatus: 503},
	{
		name:       "queue_full",
		in:         MapInput{StatusCode: 503, Reason: ErrorReasonQueueFull},
		wantCode:   apierror.CodeProviderUnavailable,
		wantStatus: 503,
	},
	{
		name:       "circuit_open",
		in:         MapInput{StatusCode: 503, Reason: ErrorReasonCircuitOpen},
		wantCode:   apierror.CodeProviderUnavailable,
		wantStatus: 503,
	},
	{
		name:       "transport",
		in:         MapInput{TransportErr: errors.New("dial tcp: connection refused")},
		wantCode:   apierror.CodeProviderUnavailable,
		wantStatus: 503,
	},
	{name: "canceled", in: MapInput{TransportErr: context.Canceled}, wantNil: true},
	{
		name: "transport_with_status",
		in: MapInput{
			TransportErr: errors.New("partial"),
			StatusCode:   502,
		},
		wantCode:   apierror.CodeProviderUnavailable,
		wantStatus: 503,
	},
}

func TestMapProviderError_core(t *testing.T) {
	t.Parallel()
	runMapCases(t, mapProviderCoreCases)
}

func TestMapProviderError_serverAndTransport(t *testing.T) {
	t.Parallel()
	runMapCases(t, mapProviderServerCases)
}

func TestMapError_entrypoints(t *testing.T) {
	t.Parallel()
	runMapErrorCases(t)
}

func TestSanitizeProviderDetail(t *testing.T) {
	t.Parallel()
	cases := []struct {
		in, want string
	}{
		{"  Invalid request parameter  ", "Invalid request parameter"},
		{"missing messages field", "missing messages field"},
		{"Invalid API key sk-live-abcdefg", ""},
		{"key sk-live-abcdefg leaked", ""},
		{"Bearer tok123", ""},
		{"ok message", ""},
		{"", ""},
	}
	for _, tc := range cases {
		if got := sanitizeProviderDetail(tc.in); got != tc.want {
			t.Fatalf("in=%q got=%q want=%q", tc.in, got, tc.want)
		}
	}
}

func runMapCases(t *testing.T, cases []mapCase) {
	t.Helper()
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := MapProviderError(tc.in)
			if tc.wantNil {
				if got != nil {
					t.Fatalf("expected nil, got %+v", got)
				}
				return
			}
			assertMapped(t, got, tc.wantCode, tc.wantStatus)
			if tc.wantRetry != 0 && got.RetryAfter != tc.wantRetry {
				t.Fatalf("RetryAfter=%v want %v", got.RetryAfter, tc.wantRetry)
			}
		})
	}
}

func runMapErrorCases(t *testing.T) {
	t.Helper()
	cases := []struct {
		name       string
		err        error
		wantWrite  bool
		wantCode   apierror.Code
		wantStatus int
		wantDetail string
	}{
		{
			name: "safe_400_detail",
			err: &ProviderError{
				ProviderName:   "openai",
				StatusCode:     http.StatusBadRequest,
				ProviderErrMsg: "Invalid type for messages",
				ProviderBody:   []byte(`{"error":{"message":"secret sk-abc123"}}`),
			},
			wantWrite:  true,
			wantCode:   apierror.CodeInvalidRequest,
			wantStatus: http.StatusBadRequest,
			wantDetail: "Invalid type for messages",
		},
		{
			name: "unsafe_detail_dropped",
			err: &ProviderError{
				StatusCode:     http.StatusBadRequest,
				ProviderErrMsg: "something weird with key material",
			},
			wantWrite:  true,
			wantCode:   apierror.CodeInvalidRequest,
			wantStatus: http.StatusBadRequest,
			wantDetail: msgInvalidRequest,
		},
		{
			name: "circuit_open_reason",
			err: &ProviderError{
				ProviderName:   "openaicompatible",
				StatusCode:     http.StatusServiceUnavailable,
				ProviderErrMsg: "circuit breaker open",
				Reason:         ErrorReasonCircuitOpen,
			},
			wantWrite:  true,
			wantCode:   apierror.CodeProviderUnavailable,
			wantStatus: http.StatusServiceUnavailable,
			wantDetail: "Self-hosted LLM circuit breaker is open",
		},
		{
			name: "queue_full_reason",
			err: &ProviderError{
				ProviderName:   "openaicompatible",
				StatusCode:     http.StatusServiceUnavailable,
				ProviderErrMsg: "queue full",
				Reason:         ErrorReasonQueueFull,
			},
			wantWrite:  true,
			wantCode:   apierror.CodeProviderUnavailable,
			wantStatus: http.StatusServiceUnavailable,
			wantDetail: "Self-hosted LLM backend queue is full",
		},
		{
			name:       "deadline",
			err:        context.DeadlineExceeded,
			wantWrite:  true,
			wantCode:   apierror.CodeProviderTimeout,
			wantStatus: http.StatusGatewayTimeout,
			wantDetail: msgProviderTimeout,
		},
		{
			name:       "transport_generic",
			err:        errors.New("connection reset"),
			wantWrite:  true,
			wantCode:   apierror.CodeProviderUnavailable,
			wantStatus: http.StatusServiceUnavailable,
			wantDetail: msgProviderUnavailable,
		},
		{
			name:      "canceled",
			err:       context.Canceled,
			wantWrite: false,
		},
		{
			name:      "nil",
			err:       nil,
			wantWrite: false,
		},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			mapped, write := MapError(tc.err)
			if write != tc.wantWrite {
				t.Fatalf("write=%v want %v", write, tc.wantWrite)
			}
			if !tc.wantWrite {
				return
			}
			assertMapped(t, mapped, tc.wantCode, tc.wantStatus)
			if mapped.Detail != tc.wantDetail {
				t.Fatalf("detail=%q want %q", mapped.Detail, tc.wantDetail)
			}
		})
	}
}

func assertMapped(t *testing.T, got *apierror.Error, code apierror.Code, status int) {
	t.Helper()
	if got == nil {
		t.Fatal("expected mapped error")
	}
	if got.Code != code {
		t.Fatalf("code: got %s want %s", got.Code, code)
	}
	if got.HTTPStatus != status {
		t.Fatalf("status: got %d want %d", got.HTTPStatus, status)
	}
}
