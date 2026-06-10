package validation

import (
	"strconv"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

const (
	fieldCodeTooLong     = "TOO_LONG"
	fieldCodeTooMany     = "TOO_MANY"
	fieldCodeInvalidEnum = "INVALID_ENUM"
)

var allowedRoles = map[string]struct{}{
	"system":    {},
	"user":      {},
	"assistant": {},
	"tool":      {},
}

// ValidateChatCompletionRequest returns all semantic validation failures.
func ValidateChatCompletionRequest(req *llm.ChatCompletionRequest) []apierror.FieldError {
	if req == nil {
		return []apierror.FieldError{{
			Field: "body", Code: fieldCodeRequired, Message: "request body is required",
		}}
	}
	var out []apierror.FieldError
	model := strings.TrimSpace(req.Model)
	if model == "" {
		out = append(out, apierror.FieldError{Field: "model", Code: fieldCodeRequired, Message: "model is required"})
	} else if len(model) > MaxModelNameLength {
		out = append(out, apierror.FieldError{
			Field: "model", Code: fieldCodeTooLong,
			Message: "model exceeds maximum length",
		})
	}
	if len(req.Messages) == 0 {
		out = append(out, apierror.FieldError{
			Field: "messages", Code: fieldCodeRequired, Message: "messages must contain at least one message",
		})
	}
	if len(req.Messages) > MaxMessagesPerRequest {
		out = append(out, apierror.FieldError{
			Field: "messages", Code: fieldCodeTooMany,
			Message: "messages exceeds maximum count",
		})
	}
	for i, msg := range req.Messages {
		role := strings.TrimSpace(msg.Role)
		if role == "" {
			out = append(out, apierror.FieldError{
				Field: msgField(i, "role"), Code: fieldCodeRequired, Message: "role is required",
			})
		} else if _, ok := allowedRoles[role]; !ok {
			out = append(out, apierror.FieldError{
				Field: msgField(i, "role"), Code: fieldCodeInvalidEnum,
				Message: "role must be one of system, user, assistant, tool",
			})
		}
		if len(msg.Content) > MaxMessageContentBytes {
			out = append(out, apierror.FieldError{
				Field: msgField(i, "content"), Code: fieldCodeTooLong,
				Message: "message content exceeds maximum size",
			})
		}
	}
	if req.Temperature != nil {
		t := *req.Temperature
		if t < MinTemperature || t > MaxTemperature {
			out = append(out, apierror.FieldError{
				Field: "temperature", Code: fieldCodeInvalidEnum,
				Message: "temperature must be between 0 and 2",
			})
		}
	}
	if req.MaxTokens != nil {
		if *req.MaxTokens <= 0 {
			out = append(out, apierror.FieldError{
				Field: "max_tokens", Code: fieldCodeInvalidEnum,
				Message: "max_tokens must be greater than 0",
			})
		} else if *req.MaxTokens > MaxChatMaxTokens {
			out = append(out, apierror.FieldError{
				Field: "max_tokens", Code: fieldCodeTooLong,
				Message: "max_tokens exceeds maximum allowed value",
			})
		}
	}
	return out
}

func msgField(index int, name string) string {
	return "messages[" + strconv.Itoa(index) + "]." + name
}
