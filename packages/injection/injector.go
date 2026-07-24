// Package injection inserts agent directive text into LLM message arrays.
package injection

import (
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

// InjectionMode selects how Inject places directive text in the messages array.
// Values match directives.injection_mode in Postgres (ADR-0030 / ADR-0031).
type InjectionMode string

const (
	// ModeSystemFirst places the directive as the first system message.
	// Existing messages (including other system messages) follow it.
	ModeSystemFirst InjectionMode = "system_first"
	// ModeSystemAppend places the directive after the leading contiguous
	// system block. If there is no leading system message, it becomes first.
	ModeSystemAppend InjectionMode = "system_append"
	// ModeUserPrepend rewrites the first user message as
	// [DIRECTIVE]: <content>\n\n<original>. If no user message exists, Inject
	// returns an independent shallow copy and leaves content unchanged.
	ModeUserPrepend InjectionMode = "user_prepend"

	roleSystem = "system"
	roleUser   = "user"

	userPrependPrefix = "[DIRECTIVE]: "
)

// ParseMode maps a stored or resolved mode string to InjectionMode.
// Empty or unknown values fall back to ModeSystemFirst so the hot path never
// rejects a request for a misspelled or newly introduced enum value.
func ParseMode(raw string) InjectionMode {
	mode := InjectionMode(strings.TrimSpace(raw))
	switch mode {
	case ModeSystemFirst, ModeSystemAppend, ModeUserPrepend:
		return mode
	default:
		return ModeSystemFirst
	}
}

// Inject returns a new messages slice with the directive applied per mode.
// The input slice is never mutated. Whitespace-only directive content is treated
// as empty and yields an independent shallow copy (nil stays nil). Unknown modes
// are normalized via ParseMode to ModeSystemFirst.
func Inject(messages []provider.Message, directive string, mode InjectionMode) []provider.Message {
	if strings.TrimSpace(directive) == "" {
		return copyMessages(messages)
	}
	switch ParseMode(string(mode)) {
	case ModeSystemAppend:
		return injectSystemAppend(messages, directive)
	case ModeUserPrepend:
		return injectUserPrepend(messages, directive)
	default:
		return injectSystemFirst(messages, directive)
	}
}

func injectSystemFirst(messages []provider.Message, directive string) []provider.Message {
	out := make([]provider.Message, 0, len(messages)+1)
	out = append(out, provider.Message{Role: roleSystem, Content: directive})
	return append(out, messages...)
}

func injectSystemAppend(messages []provider.Message, directive string) []provider.Message {
	n := leadingSystemCount(messages)
	out := make([]provider.Message, 0, len(messages)+1)
	out = append(out, messages[:n]...)
	out = append(out, provider.Message{Role: roleSystem, Content: directive})
	return append(out, messages[n:]...)
}

func injectUserPrepend(messages []provider.Message, directive string) []provider.Message {
	idx := firstUserIndex(messages)
	if idx < 0 {
		return copyMessages(messages)
	}
	out := copyMessages(messages)
	out[idx].Content = userPrependPrefix + directive + "\n\n" + messages[idx].Content
	return out
}

func leadingSystemCount(messages []provider.Message) int {
	n := 0
	for _, m := range messages {
		if m.Role != roleSystem {
			break
		}
		n++
	}
	return n
}

func firstUserIndex(messages []provider.Message) int {
	for i, m := range messages {
		if m.Role == roleUser {
			return i
		}
	}
	return -1
}

func copyMessages(messages []provider.Message) []provider.Message {
	if messages == nil {
		return nil
	}
	out := make([]provider.Message, len(messages))
	copy(out, messages)
	return out
}
