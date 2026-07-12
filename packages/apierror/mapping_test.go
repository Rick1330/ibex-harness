package apierror_test

import (
	"net/http"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/apierror"
	"google.golang.org/grpc/codes"
)

func TestHTTPStatus_allRegisteredCodes(t *testing.T) {
	t.Parallel()

	cases := []struct {
		code   apierror.Code
		status int
	}{
		{apierror.CodeMissingToken, http.StatusUnauthorized},
		{apierror.CodeInvalidToken, http.StatusUnauthorized},
		{apierror.CodeInsufficientPermissions, http.StatusForbidden},
		{apierror.CodeInvalidJSON, http.StatusBadRequest},
		{apierror.CodeInvalidRequest, http.StatusBadRequest},
		{apierror.CodeProviderNotConfigured, http.StatusNotImplemented},
		{apierror.CodePayloadTooLarge, http.StatusRequestEntityTooLarge},
		{apierror.CodeUnsupportedMediaType, http.StatusUnsupportedMediaType},
		{apierror.CodeValidationError, http.StatusBadRequest},
		{apierror.CodeMethodNotAllowed, http.StatusMethodNotAllowed},
		{apierror.CodeMissingAgentID, http.StatusBadRequest},
		{apierror.CodeAgentNotAuthorized, http.StatusForbidden},
		{apierror.CodeAgentSuspended, http.StatusForbidden},
		{apierror.CodeRateLimited, http.StatusTooManyRequests},
		{apierror.CodeInternalError, http.StatusInternalServerError},
		{apierror.CodeServiceDegraded, http.StatusServiceUnavailable},
		{apierror.CodeAuthUnavailable, http.StatusServiceUnavailable},
		{apierror.CodeProviderUnavailable, http.StatusServiceUnavailable},
		{apierror.CodeProviderTimeout, http.StatusGatewayTimeout},
	}
	for _, tc := range cases {
		if got := apierror.HTTPStatus(tc.code); got != tc.status {
			t.Fatalf("%s HTTPStatus = %d, want %d", tc.code, got, tc.status)
		}
	}
}

func TestHTTPStatus_unknownCode(t *testing.T) {
	t.Parallel()

	if got := apierror.HTTPStatus(apierror.Code("UNKNOWN_CODE")); got != http.StatusInternalServerError {
		t.Fatalf("unknown: %d", got)
	}
}

func TestGRPCCode_allRegisteredCodes(t *testing.T) {
	t.Parallel()

	cases := []struct {
		code apierror.Code
		grpc codes.Code
	}{
		{apierror.CodeMissingToken, codes.Unauthenticated},
		{apierror.CodeInvalidToken, codes.Unauthenticated},
		{apierror.CodeInsufficientPermissions, codes.PermissionDenied},
		{apierror.CodeInvalidJSON, codes.InvalidArgument},
		{apierror.CodeInvalidRequest, codes.InvalidArgument},
		{apierror.CodeProviderNotConfigured, codes.FailedPrecondition},
		{apierror.CodePayloadTooLarge, codes.InvalidArgument},
		{apierror.CodeUnsupportedMediaType, codes.InvalidArgument},
		{apierror.CodeValidationError, codes.InvalidArgument},
		{apierror.CodeMethodNotAllowed, codes.InvalidArgument},
		{apierror.CodeMissingAgentID, codes.InvalidArgument},
		{apierror.CodeAgentNotAuthorized, codes.PermissionDenied},
		{apierror.CodeAgentSuspended, codes.PermissionDenied},
		{apierror.CodeRateLimited, codes.ResourceExhausted},
		{apierror.CodeInternalError, codes.Internal},
		{apierror.CodeServiceDegraded, codes.Unavailable},
		{apierror.CodeAuthUnavailable, codes.Unavailable},
		{apierror.CodeProviderUnavailable, codes.Unavailable},
		{apierror.CodeProviderTimeout, codes.DeadlineExceeded},
	}
	for _, tc := range cases {
		if got := apierror.GRPCCode(tc.code); got != tc.grpc {
			t.Fatalf("%s GRPCCode = %v, want %v", tc.code, got, tc.grpc)
		}
	}
}

func TestGRPCCode_unknownCode(t *testing.T) {
	t.Parallel()

	if got := apierror.GRPCCode(apierror.Code("UNKNOWN_CODE")); got != codes.Internal {
		t.Fatalf("unknown: %v", got)
	}
}
