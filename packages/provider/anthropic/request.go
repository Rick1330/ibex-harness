package anthropic

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

type anthropicRequest struct {
	Model       string             `json:"model"`
	Messages    []anthropicMessage `json:"messages"`
	MaxTokens   int                `json:"max_tokens"`
	System      string             `json:"system,omitempty"`
	Temperature *float64           `json:"temperature,omitempty"`
	Stream      bool               `json:"stream"`
}

type anthropicMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// allowedPassthroughKeys is an allowlist: Anthropic's dialect has many powerful
// fields (tools, thinking, etc.) that this text-only milestone must not accept
// from client passthrough. Prefer deny-by-default over OpenAI's deny-list shape.
var allowedPassthroughKeys = map[string]struct{}{
	"top_p":           {},
	"stop_sequences":  {},
	"metadata":        {},
	"service_tier":    {},
}

func marshalAnthropicRequestBody(req provider.Request, defaultTokens int) ([]byte, error) {
	out, err := toAnthropicRequest(req, defaultTokens)
	if err != nil {
		return nil, err
	}
	if len(req.PassthroughFields) == 0 {
		return json.Marshal(out)
	}
	raw, err := json.Marshal(out)
	if err != nil {
		return nil, err
	}
	var merged map[string]any
	if err := json.Unmarshal(raw, &merged); err != nil {
		return nil, err
	}
	for k, v := range req.PassthroughFields {
		if _, ok := allowedPassthroughKeys[k]; !ok {
			continue
		}
		merged[k] = v
	}
	return json.Marshal(merged)
}

func toAnthropicRequest(req provider.Request, defaultTokens int) (anthropicRequest, error) {
	system, turns, err := extractSystemAndTurns(req.Messages)
	if err != nil {
		return anthropicRequest{}, err
	}
	maxTokens := req.MaxTokens
	if maxTokens <= 0 {
		maxTokens = defaultTokens
	}
	return anthropicRequest{
		Model:       req.Model,
		System:      system,
		MaxTokens:   maxTokens,
		Temperature: req.Temperature,
		Stream:      req.Stream,
		Messages:    turns,
	}, nil
}

func extractSystemAndTurns(messages []provider.Message) (system string, turns []anthropicMessage, err error) {
	i := 0
	var sysParts []string
	for i < len(messages) && strings.EqualFold(messages[i].Role, "system") {
		if s := strings.TrimSpace(messages[i].Content); s != "" {
			sysParts = append(sysParts, s)
		}
		i++
	}
	if len(sysParts) > 0 {
		system = strings.Join(sysParts, "\n\n")
	}

	rest := messages[i:]
	if len(rest) == 0 {
		return system, nil, &provider.ProviderError{
			ProviderName:   "anthropic",
			StatusCode:     http.StatusBadRequest,
			ProviderErrMsg: "anthropic requires at least one non-system message",
		}
	}

	coalesced := coalesceTurns(rest)
	if !strings.EqualFold(coalesced[0].Role, "user") {
		return "", nil, &provider.ProviderError{
			ProviderName:   "anthropic",
			StatusCode:     http.StatusBadRequest,
			ProviderErrMsg: "anthropic conversation must start with a user turn after system messages",
		}
	}
	turns = make([]anthropicMessage, 0, len(coalesced))
	for _, m := range coalesced {
		role := strings.ToLower(strings.TrimSpace(m.Role))
		switch role {
		case "user", "assistant":
			turns = append(turns, anthropicMessage{Role: role, Content: m.Content})
		case "tool":
			return "", nil, &provider.ProviderError{
				ProviderName:   "anthropic",
				StatusCode:     http.StatusBadRequest,
				ProviderErrMsg: "anthropic tool-role messages are not supported in this adapter",
			}
		default:
			return "", nil, &provider.ProviderError{
				ProviderName:   "anthropic",
				StatusCode:     http.StatusBadRequest,
				ProviderErrMsg: fmt.Sprintf("unsupported message role %q for anthropic", m.Role),
			}
		}
	}
	return system, turns, nil
}

func coalesceTurns(messages []provider.Message) []provider.Message {
	if len(messages) == 0 {
		return nil
	}
	out := make([]provider.Message, 0, len(messages))
	curRole := strings.ToLower(strings.TrimSpace(messages[0].Role))
	var content strings.Builder
	content.WriteString(messages[0].Content)

	flush := func() {
		out = append(out, provider.Message{Role: curRole, Content: content.String()})
		content.Reset()
	}

	for i := 1; i < len(messages); i++ {
		role := strings.ToLower(strings.TrimSpace(messages[i].Role))
		if role == curRole {
			if messages[i].Content == "" {
				continue
			}
			if content.Len() > 0 {
				content.WriteString("\n\n")
			}
			content.WriteString(messages[i].Content)
			continue
		}
		flush()
		curRole = role
		content.WriteString(messages[i].Content)
	}
	flush()
	return out
}
