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
	"top_p":          {},
	"stop_sequences": {},
	"metadata":       {},
	"service_tier":   {},
}

func marshalAnthropicRequestBody(req provider.Request, defaultTokens int) ([]byte, error) {
	out, err := toAnthropicRequest(req, defaultTokens)
	if err != nil {
		return nil, err
	}
	if len(req.PassthroughFields) == 0 {
		return json.Marshal(out)
	}
	return mergeAllowlistedPassthrough(out, req.PassthroughFields)
}

func mergeAllowlistedPassthrough(out anthropicRequest, fields map[string]any) ([]byte, error) {
	raw, err := json.Marshal(out)
	if err != nil {
		return nil, err
	}
	var merged map[string]any
	if err := json.Unmarshal(raw, &merged); err != nil {
		return nil, err
	}
	for k, v := range fields {
		if _, ok := allowedPassthroughKeys[k]; ok {
			merged[k] = v
		}
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

func extractSystemAndTurns(messages []provider.Message) (string, []anthropicMessage, error) {
	system, rest := peelSystemPrefix(messages)
	system, rest = foldMidConversationSystem(system, rest)
	if len(rest) == 0 {
		return system, nil, badRequest("anthropic requires at least one non-system message")
	}
	coalesced := coalesceTurns(rest)
	if !strings.EqualFold(coalesced[0].Role, "user") {
		return "", nil, badRequest("anthropic conversation must start with a user turn after system messages")
	}
	turns, err := mapAnthropicTurns(coalesced)
	if err != nil {
		return "", nil, err
	}
	return system, turns, nil
}

func peelSystemPrefix(messages []provider.Message) (system string, rest []provider.Message) {
	i := 0
	var parts []string
	for i < len(messages) && strings.EqualFold(messages[i].Role, "system") {
		if s := strings.TrimSpace(messages[i].Content); s != "" {
			parts = append(parts, s)
		}
		i++
	}
	if len(parts) > 0 {
		system = strings.Join(parts, "\n\n")
	}
	return system, messages[i:]
}

// foldMidConversationSystem moves non-leading system turns into the top-level
// system string so directive injection / client order quirks do not 400.
func foldMidConversationSystem(system string, messages []provider.Message) (string, []provider.Message) {
	if len(messages) == 0 {
		return system, nil
	}
	out := make([]provider.Message, 0, len(messages))
	for _, m := range messages {
		if !strings.EqualFold(strings.TrimSpace(m.Role), "system") {
			out = append(out, m)
			continue
		}
		if s := strings.TrimSpace(m.Content); s != "" {
			if system != "" {
				system += "\n\n"
			}
			system += s
		}
	}
	return system, out
}

func mapAnthropicTurns(messages []provider.Message) ([]anthropicMessage, error) {
	turns := make([]anthropicMessage, 0, len(messages))
	for _, m := range messages {
		role := strings.ToLower(strings.TrimSpace(m.Role))
		switch role {
		case "user", "assistant":
			if strings.TrimSpace(m.Content) == "" {
				return nil, badRequest("anthropic turn content must be non-empty")
			}
			turns = append(turns, anthropicMessage{Role: role, Content: m.Content})
		case "tool":
			return nil, badRequest("anthropic tool-role messages are not supported in this adapter")
		default:
			return nil, badRequest(fmt.Sprintf("unsupported message role %q for anthropic", m.Role))
		}
	}
	return turns, nil
}

func badRequest(msg string) error {
	return &provider.ProviderError{
		ProviderName:   "anthropic",
		StatusCode:     http.StatusBadRequest,
		ProviderErrMsg: msg,
	}
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
			appendCoalescedContent(&content, messages[i].Content)
			continue
		}
		flush()
		curRole = role
		content.WriteString(messages[i].Content)
	}
	flush()
	return out
}

func appendCoalescedContent(b *strings.Builder, next string) {
	if next == "" {
		return
	}
	if b.Len() > 0 {
		b.WriteString("\n\n")
	}
	b.WriteString(next)
}
