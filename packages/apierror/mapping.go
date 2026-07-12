package apierror

import (
	"net/http"

	"google.golang.org/grpc/codes"
)

// HTTPStatus returns the HTTP status code for a given error code.
// Returns 500 for unknown codes.
func HTTPStatus(code Code) int {
	if status, ok := httpStatusByCode[code]; ok {
		return status
	}
	return http.StatusInternalServerError
}

// GRPCCode returns the gRPC status code for a given error code.
func GRPCCode(code Code) codes.Code {
	if grpc, ok := grpcCodeByCode[code]; ok {
		return grpc
	}
	return codes.Internal
}

var httpStatusByCode = map[Code]int{
	CodeMissingToken:            http.StatusUnauthorized,
	CodeInvalidToken:            http.StatusUnauthorized,
	CodeInsufficientPermissions: http.StatusForbidden,
	CodeInvalidJSON:             http.StatusBadRequest,
	CodeInvalidRequest:          http.StatusBadRequest,
	CodeProviderNotConfigured:   http.StatusNotImplemented,
	CodePayloadTooLarge:         http.StatusRequestEntityTooLarge,
	CodeUnsupportedMediaType:    http.StatusUnsupportedMediaType,
	CodeValidationError:         http.StatusBadRequest,
	CodeMethodNotAllowed:        http.StatusMethodNotAllowed,
	CodeMissingAgentID:          http.StatusBadRequest,
	CodeAgentNotAuthorized:      http.StatusForbidden,
	CodeAgentSuspended:          http.StatusForbidden,
	CodeRateLimited:             http.StatusTooManyRequests,
	CodeInternalError:           http.StatusInternalServerError,
	CodeServiceDegraded:         http.StatusServiceUnavailable,
	CodeAuthUnavailable:         http.StatusServiceUnavailable,
	CodeProviderUnavailable:     http.StatusServiceUnavailable,
	CodeProviderTimeout:         http.StatusGatewayTimeout,
}

var grpcCodeByCode = map[Code]codes.Code{
	CodeMissingToken:            codes.Unauthenticated,
	CodeInvalidToken:            codes.Unauthenticated,
	CodeInsufficientPermissions: codes.PermissionDenied,
	CodeInvalidJSON:             codes.InvalidArgument,
	CodeInvalidRequest:          codes.InvalidArgument,
	CodeProviderNotConfigured:   codes.FailedPrecondition,
	CodePayloadTooLarge:         codes.InvalidArgument,
	CodeUnsupportedMediaType:    codes.InvalidArgument,
	CodeValidationError:         codes.InvalidArgument,
	CodeMethodNotAllowed:        codes.InvalidArgument,
	CodeMissingAgentID:          codes.InvalidArgument,
	CodeAgentNotAuthorized:      codes.PermissionDenied,
	CodeAgentSuspended:          codes.PermissionDenied,
	CodeRateLimited:             codes.ResourceExhausted,
	CodeInternalError:           codes.Internal,
	CodeServiceDegraded:         codes.Unavailable,
	CodeAuthUnavailable:         codes.Unavailable,
	CodeProviderUnavailable:     codes.Unavailable,
	CodeProviderTimeout:         codes.DeadlineExceeded,
}
