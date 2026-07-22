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
	assertMapped(t, got, apierror.CodeRateLimited, http.StatusTooManyRequests)
	if got.RetryAfter != 30*time.Second {
		t.Fatalf("RetryAfter=%v", got.RetryAfter)
	}
}

func TestMapProviderError_OpenAI401(t *testing.T) {
	t.Parallel()
	got := MapProviderError(MapInput{ProviderName: "openai", StatusCode: http.StatusUnauthorized})
	assertMapped(t, got, apierror.CodeProviderUnavailable, http.StatusServiceUnavailable)
}

func TestMapProviderError_Timeout(t *testing.T) {
	t.Parallel()
	got := MapProviderError(MapInput{TransportErr: context.DeadlineExceeded})
	assertMapped(t, got, apierror.CodeProviderTimeout, http.StatusGatewayTimeout)
}

func TestMapProviderError_clientErrors(t *testing.T) {
	t.Parallel()
	runMapCases(t, []mapCase{
		{name: "400", in: MapInput{StatusCode: 400, SafeMessage: "missing messages"}, code: apierror.CodeInvalidRequest, status: 400},
		{name: "403", in: MapInput{StatusCode: 403}, code: apierror.CodeProviderUnavailable, status: 503},
		{name: "404", in: MapInput{StatusCode: 404}, code: apierror.CodeProviderUnavailable, status: 503},
	})
}

func TestMapProviderError_serverAndTransport(t *testing.T) {
	t.Parallel()
	runMapCases(t, []mapCase{
		{name: "500", in: MapInput{StatusCode: 500}, code: apierror.CodeProviderUnavailable, status: 503},
		{name: "502", in: MapInput{StatusCode: 502}, code: apierror.CodeProviderUnavailable, status: 503},
		{name: "503", in: MapInput{StatusCode: 503}, code: apierror.CodeProviderUnavailable, status: 503},
		{name: "504", in: MapInput{StatusCode: 504}, code: apierror.CodeProviderUnavailable, status: 503},
		{name: "transport", in: MapInput{TransportErr: errors.New("dial tcp: connection refused")}, code: apierror.CodeProviderUnavailable, status: 503},
		{name: "canceled", in: MapInput{TransportErr: context.Canceled}, wantNil: true},
	})
}

func TestMapError_providerBadRequest(t *testing.T) {
	t.Parallel()
	mapped, write := MapError(&ProviderError{
		ProviderName:   "openai",
		StatusCode:     http.StatusBadRequest,
		ProviderErrMsg: "Invalid type for messages",
		ProviderBody:   []byte(`{"error":{"message":"secret sk-abc123 should not leak via body path"}}`),
	})
	if !write {
		t.Fatal("expected write")
	}
	assertMapped(t, mapped, apierror.CodeInvalidRequest, http.StatusBadRequest)
	if mapped.Detail != "Invalid type for messages" {
		t.Fatalf("detail=%q", mapped.Detail)
	}
	if strings.Contains(mapped.Detail, "sk-") {
		t.Fatal("detail must not contain secrets from body")
	}
}

func TestMapError_unsafeDetailDropped(t *testing.T) {
	t.Parallel()
	mapped, write := MapError(&ProviderError{
		StatusCode:     http.StatusBadRequest,
		ProviderErrMsg: "something weird with key material",
	})
	if !write {
		t.Fatal("expected write")
	}
	assertMapped(t, mapped, apierror.CodeInvalidRequest, http.StatusBadRequest)
	if mapped.Detail != msgInvalidRequest {
		t.Fatalf("expected generic detail, got %q", mapped.Detail)
	}
}

func TestMapError_canceledSuppressesWrite(t *testing.T) {
	t.Parallel()
	_, write := MapError(context.Canceled)
	if write {
		t.Fatal("canceled must suppress write")
	}
}

func TestSanitizeProviderDetail(t *testing.T) {
	t.Parallel()
	if got := sanitizeProviderDetail("  Invalid request parameter  "); got != "Invalid request parameter" {
		t.Fatalf("allowlist: %q", got)
	}
	if got := sanitizeProviderDetail("missing messages field"); got != "missing messages field" {
		t.Fatalf("missing: %q", got)
	}
	if got := sanitizeProviderDetail("key sk-live-abcdefg leaked"); got != "" {
		t.Fatalf("secret: %q", got)
	}
	if got := sanitizeProviderDetail("Bearer tok123"); got != "" {
		t.Fatalf("bearer: %q", got)
	}
	if got := sanitizeProviderDetail("ok message"); got != "" {
		t.Fatalf("non-validation free text must be empty: %q", got)
	}
	if got := sanitizeProviderDetail(""); got != "" {
		t.Fatalf("empty: %q", got)
	}
}

type mapCase struct {
	name    string
	in      MapInput
	code    apierror.Code
	status  int
	wantNil bool
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
			assertMapped(t, got, tc.code, tc.status)
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
