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
	out = append(out, validateModel(req.Model)...)
	out = append(out, validateMessages(req.Messages)...)
	out = append(out, validateTemperature(req.Temperature)...)
	out = append(out, validateMaxTokens(req.MaxTokens)...)
	return out
}

func validateModel(model string) []apierror.FieldError {
	model = strings.TrimSpace(model)
	if model == "" {
		return []apierror.FieldError{{Field: "model", Code: fieldCodeRequired, Message: "model is required"}}
	}
	if len(model) > MaxModelNameLength {
		return []apierror.FieldError{{Field: "model", Code: fieldCodeTooLong, Message: "model exceeds maximum length"}}
	}
	return nil
}

func validateMessages(msgs []llm.Message) []apierror.FieldError {
	var out []apierror.FieldError
	if len(msgs) == 0 {
		out = append(out, apierror.FieldError{
			Field: "messages", Code: fieldCodeRequired, Message: "messages must contain at least one message",
		})
	}
	if len(msgs) > MaxMessagesPerRequest {
		out = append(out, apierror.FieldError{
			Field: "messages", Code: fieldCodeTooMany, Message: "messages exceeds maximum count",
		})
	}
	for i, msg := range msgs {
		out = append(out, validateMessage(i, msg)...)
	}
	return out
}

func validateMessage(i int, msg llm.Message) []apierror.FieldError {
	var out []apierror.FieldError
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
			Field: msgField(i, "content"), Code: fieldCodeTooLong, Message: "message content exceeds maximum size",
		})
	}
	return out
}

func validateTemperature(t *float64) []apierror.FieldError {
	if t == nil {
		return nil
	}
	if *t < MinTemperature || *t > MaxTemperature {
		return []apierror.FieldError{{
			Field: "temperature", Code: fieldCodeInvalidEnum, Message: "temperature must be between 0 and 2",
		}}
	}
	return nil
}

func validateMaxTokens(v *int) []apierror.FieldError {
	if v == nil {
		return nil
	}
	if *v <= 0 {
		return []apierror.FieldError{{
			Field: "max_tokens", Code: fieldCodeInvalidEnum, Message: "max_tokens must be greater than 0",
		}}
	}
	if *v > MaxChatMaxTokens {
		return []apierror.FieldError{{
			Field: "max_tokens", Code: fieldCodeTooLong, Message: "max_tokens exceeds maximum allowed value",
		}}
	}
	return nil
}

func msgField(index int, name string) string {
	return "messages[" + strconv.Itoa(index) + "]." + name
}
