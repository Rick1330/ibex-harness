package validation

import (
	"strings"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/google/uuid"
)

const (
	fieldCodeRequired      = "REQUIRED"
	fieldCodeInvalidFormat = "INVALID_FORMAT"
)

// ValidateUUIDField returns a field error when value is not a valid UUID.
func ValidateUUIDField(field, value string) *apierror.FieldError {
	value = strings.TrimSpace(value)
	if value == "" {
		return &apierror.FieldError{
			Field:   field,
			Code:    fieldCodeRequired,
			Message: field + " is required",
		}
	}
	if _, err := uuid.Parse(value); err != nil {
		return &apierror.FieldError{
			Field:   field,
			Code:    fieldCodeInvalidFormat,
			Message: field + " must be a valid UUID",
		}
	}
	return nil
}
