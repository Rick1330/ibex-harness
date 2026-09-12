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
	CodeMissingToken:               http.StatusUnauthorized,
	CodeInvalidToken:               http.StatusUnauthorized,
	CodeInsufficientPermissions:    http.StatusForbidden,
	CodePermissionElevationDenied:  http.StatusForbidden,
	CodeInvalidJSON:                http.StatusBadRequest,
	CodeInvalidRequest:             http.StatusBadRequest,
	CodeProviderNotConfigured:      http.StatusNotImplemented,
	CodeModelNotAllowed:            http.StatusForbidden,
	CodePayloadTooLarge:            http.StatusRequestEntityTooLarge,
	CodeUnsupportedMediaType:       http.StatusUnsupportedMediaType,
	CodeValidationError:            http.StatusBadRequest,
	CodeInvalidCredential:          http.StatusUnprocessableEntity,
	CodeMethodNotAllowed:           http.StatusMethodNotAllowed,
	CodeMissingAgentID:             http.StatusBadRequest,
	CodeAgentNotAuthorized:         http.StatusForbidden,
	CodeAgentSuspended:             http.StatusForbidden,
	CodeOrgSuspended:               http.StatusForbidden,
	CodeLastOwnerProtected:         http.StatusConflict,
	CodeModelPolicyPatternConflict: http.StatusConflict,
	CodeAgentSlugConflict:          http.StatusConflict,
	CodeAgentHasSessions:           http.StatusConflict,
	CodeAgentStatusConflict:        http.StatusConflict,
	CodeRateLimited:                http.StatusTooManyRequests,
	CodeIdempotencyKeyReuse:        http.StatusConflict,
	CodeIdempotencyInProgress:      http.StatusConflict,
	CodeInternalError:              http.StatusInternalServerError,
	CodeServiceDegraded:            http.StatusServiceUnavailable,
	CodeAuthUnavailable:            http.StatusServiceUnavailable,
	CodeProviderUnavailable:        http.StatusServiceUnavailable,
	CodeProviderTimeout:            http.StatusGatewayTimeout,
}

var grpcCodeByCode = map[Code]codes.Code{
	CodeMissingToken:               codes.Unauthenticated,
	CodeInvalidToken:               codes.Unauthenticated,
	CodeInsufficientPermissions:    codes.PermissionDenied,
	CodePermissionElevationDenied:  codes.PermissionDenied,
	CodeInvalidJSON:                codes.InvalidArgument,
	CodeInvalidRequest:             codes.InvalidArgument,
	CodeProviderNotConfigured:      codes.FailedPrecondition,
	CodeModelNotAllowed:            codes.PermissionDenied,
	CodePayloadTooLarge:            codes.InvalidArgument,
	CodeUnsupportedMediaType:       codes.InvalidArgument,
	CodeValidationError:            codes.InvalidArgument,
	CodeInvalidCredential:          codes.InvalidArgument,
	CodeMethodNotAllowed:           codes.InvalidArgument,
	CodeMissingAgentID:             codes.InvalidArgument,
	CodeAgentNotAuthorized:         codes.PermissionDenied,
	CodeAgentSuspended:             codes.PermissionDenied,
	CodeOrgSuspended:               codes.PermissionDenied,
	CodeLastOwnerProtected:         codes.FailedPrecondition,
	CodeModelPolicyPatternConflict: codes.AlreadyExists,
	CodeAgentSlugConflict:          codes.AlreadyExists,
	CodeAgentHasSessions:           codes.FailedPrecondition,
	CodeAgentStatusConflict:        codes.Aborted,
	CodeRateLimited:                codes.ResourceExhausted,
	CodeIdempotencyKeyReuse:        codes.AlreadyExists,
	CodeIdempotencyInProgress:      codes.Aborted,
	CodeInternalError:              codes.Internal,
	CodeServiceDegraded:            codes.Unavailable,
	CodeAuthUnavailable:            codes.Unavailable,
	CodeProviderUnavailable:        codes.Unavailable,
	CodeProviderTimeout:            codes.DeadlineExceeded,
}
