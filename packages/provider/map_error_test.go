package provider

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
)

func TestMapProviderError_OpenAI429(t *testing.T) {
	t.Parallel()
	got := MapProviderError(MapInput{
		ProviderName: "openai",
		StatusCode:   http.StatusTooManyRequests,
		RetryAfter:   30 * time.Second,
	})
	if got == nil {
		t.Fatal("expected mapped error")
	}
	if got.Code != apierror.CodeRateLimited || got.HTTPStatus != http.StatusTooManyRequests {
		t.Fatalf("got code=%s status=%d", got.Code, got.HTTPStatus)
	}
	if got.RetryAfter != 30*time.Second {
		t.Fatalf("RetryAfter=%v", got.RetryAfter)
	}
}

func TestMapProviderError_OpenAI401(t *testing.T) {
	t.Parallel()
	got := MapProviderError(MapInput{ProviderName: "openai", StatusCode: http.StatusUnauthorized})
	if got == nil || got.Code != apierror.CodeProviderUnavailable || got.HTTPStatus != http.StatusServiceUnavailable {
		t.Fatalf("got %+v", got)
	}
}

func TestMapProviderError_Timeout(t *testing.T) {
	t.Parallel()
	got := MapProviderError(MapInput{TransportErr: context.DeadlineExceeded})
	if got == nil || got.Code != apierror.CodeProviderTimeout || got.HTTPStatus != http.StatusGatewayTimeout {
		t.Fatalf("got %+v", got)
	}
}

func TestMapProviderError_table(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name       string
		in         MapInput
		wantNil    bool
		wantCode   apierror.Code
		wantStatus int
	}{
		{
			name:       "400 with safe detail",
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
		{
			name:       "500",
			in:         MapInput{StatusCode: 500},
			wantCode:   apierror.CodeProviderUnavailable,
			wantStatus: 503,
		},
		{
			name:       "502",
			in:         MapInput{StatusCode: 502},
			wantCode:   apierror.CodeProviderUnavailable,
			wantStatus: 503,
		},
		{
			name:       "503",
			in:         MapInput{StatusCode: 503},
			wantCode:   apierror.CodeProviderUnavailable,
			wantStatus: 503,
		},
		{
			name:       "504",
			in:         MapInput{StatusCode: 504},
			wantCode:   apierror.CodeProviderUnavailable,
			wantStatus: 503,
		},
		{
			name:       "transport",
			in:         MapInput{TransportErr: errors.New("dial tcp: connection refused")},
			wantCode:   apierror.CodeProviderUnavailable,
			wantStatus: 503,
		},
		{
			name:    "canceled",
			in:      MapInput{TransportErr: context.Canceled},
			wantNil: true,
		},
	}
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
			if got == nil || got.Code != tc.wantCode || got.HTTPStatus != tc.wantStatus {
				t.Fatalf("got %+v want code=%s status=%d", got, tc.wantCode, tc.wantStatus)
			}
		})
	}
}

func TestMapError_fromProviderErrorAndCancel(t *testing.T) {
	t.Parallel()
	mapped, write := MapError(&ProviderError{
		ProviderName:   "openai",
		StatusCode:     http.StatusBadRequest,
		ProviderErrMsg: "bad field",
		ProviderBody:   []byte(`{"error":{"message":"secret sk-abc123 should not leak via body path"}}`),
	})
	if !write || mapped == nil || mapped.Code != apierror.CodeInvalidRequest {
		t.Fatalf("mapped=%+v write=%v", mapped, write)
	}
	if mapped.Detail != "bad field" {
		t.Fatalf("detail=%q", mapped.Detail)
	}
	if strings.Contains(mapped.Detail, "sk-") {
		t.Fatal("detail must not contain secrets from body")
	}

	_, write = MapError(context.Canceled)
	if write {
		t.Fatal("canceled must suppress write")
	}
}

func TestSanitizeProviderDetail(t *testing.T) {
	t.Parallel()
	if got := sanitizeProviderDetail("  ok message  "); got != "ok message" {
		t.Fatalf("trim: %q", got)
	}
	if got := sanitizeProviderDetail("key sk-live-abcdefg leaked"); got != "" {
		t.Fatalf("secret: %q", got)
	}
	if got := sanitizeProviderDetail("Bearer tok123"); got != "" {
		t.Fatalf("bearer: %q", got)
	}
	long := strings.Repeat("a", 400)
	if got := sanitizeProviderDetail(long); len([]rune(got)) != maxSafeDetailRunes {
		t.Fatalf("truncate len=%d", len([]rune(got)))
	}
}
