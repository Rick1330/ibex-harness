package provider

import (
	"context"
	"errors"
	"net/http"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
)

const (
	msgInvalidRequest      = "Invalid request to LLM provider"
	msgRateLimited         = "Upstream LLM provider rate limited"
	msgProviderTimeout     = "Upstream LLM provider timed out"
	msgProviderUnavailable = "Upstream LLM provider is unavailable"
)

// MapInput is the primitive input for MapProviderError (table-driven mapping).
type MapInput struct {
	ProviderName string
	StatusCode   int // 0 when transport-only
	RetryAfter   time.Duration
	TransportErr error
	SafeMessage  string // optional sanitized 400 detail
}

// MapProviderError translates provider HTTP status or transport failure into
// the canonical IBEX apierror.Error. Never exposes API keys or raw bodies.
// ProviderName is for caller logs only — not copied into the client envelope.
func MapProviderError(in MapInput) *apierror.Error {
	if mapped, handled := mapTransport(in); handled {
		return mapped
	}
	return mapHTTPStatus(in.StatusCode, in.RetryAfter, in.SafeMessage)
}

// MapError is the handler entrypoint: unwraps ProviderError / deadline / cancel.
// write is false only for context.Canceled (caller must not write a response).
func MapError(err error) (mapped *apierror.Error, write bool) {
	if err == nil || errors.Is(err, context.Canceled) {
		return nil, false
	}
	var pe *ProviderError
	if errors.As(err, &pe) && pe != nil {
		return MapProviderError(MapInput{
			ProviderName: pe.ProviderName,
			StatusCode:   pe.StatusCode,
			RetryAfter:   pe.RetryAfter,
			SafeMessage:  sanitizeProviderDetail(pe.ProviderErrMsg),
		}), true
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return MapProviderError(MapInput{TransportErr: context.DeadlineExceeded}), true
	}
	return MapProviderError(MapInput{TransportErr: err}), true
}

func mapTransport(in MapInput) (*apierror.Error, bool) {
	if in.TransportErr == nil {
		return nil, false
	}
	if errors.Is(in.TransportErr, context.Canceled) {
		return nil, true
	}
	if errors.Is(in.TransportErr, context.DeadlineExceeded) {
		return &apierror.Error{
			Code:       apierror.CodeProviderTimeout,
			Message:    msgProviderTimeout,
			Detail:     msgProviderTimeout,
			HTTPStatus: apierror.HTTPStatus(apierror.CodeProviderTimeout),
		}, true
	}
	if in.StatusCode == 0 {
		return unavailable(), true
	}
	return nil, false
}

func mapHTTPStatus(status int, retryAfter time.Duration, safeMsg string) *apierror.Error {
	switch status {
	case http.StatusBadRequest:
		detail := safeMsg
		if detail == "" {
			detail = msgInvalidRequest
		}
		return &apierror.Error{
			Code:       apierror.CodeInvalidRequest,
			Message:    msgInvalidRequest,
			Detail:     detail,
			HTTPStatus: http.StatusBadRequest,
		}
	case http.StatusTooManyRequests:
		return &apierror.Error{
			Code:       apierror.CodeRateLimited,
			Message:    msgRateLimited,
			Detail:     msgRateLimited,
			HTTPStatus: http.StatusTooManyRequests,
			RetryAfter: retryAfter,
		}
	default:
		// 401/403/404/5xx and other upstream codes: never leak as client PAT 401/403/404.
		return unavailable()
	}
}

func unavailable() *apierror.Error {
	return &apierror.Error{
		Code:       apierror.CodeProviderUnavailable,
		Message:    msgProviderUnavailable,
		Detail:     msgProviderUnavailable,
		HTTPStatus: apierror.HTTPStatus(apierror.CodeProviderUnavailable),
	}
}
