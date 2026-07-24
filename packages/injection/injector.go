// Package injection inserts agent directive text into LLM message arrays.
package injection

import (
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

// InjectionMode controls how the directive is inserted into the messages array.
type InjectionMode string

const (
	// ModeSystemFirst inserts the directive as the first system message.
	ModeSystemFirst InjectionMode = "system_first"
	// ModeSystemAppend inserts the directive after leading system messages.
	ModeSystemAppend InjectionMode = "system_append"
	// ModeUserPrepend prepends the directive to the first user message.
	ModeUserPrepend InjectionMode = "user_prepend"

	roleSystem = "system"
	roleUser   = "user"

	userPrependPrefix = "[DIRECTIVE]: "
)

// ParseMode maps a stored / resolved mode string to InjectionMode.
// Unknown or empty values become ModeSystemFirst.
func ParseMode(raw string) InjectionMode {
	mode := InjectionMode(strings.TrimSpace(raw))
	switch mode {
	case ModeSystemFirst, ModeSystemAppend, ModeUserPrepend:
		return mode
	default:
		return ModeSystemFirst
	}
}

// Inject returns a new messages slice with the directive applied.
// Empty directive returns a shallow copy of messages (input never mutated).
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
	out := make([]provider.Message, len(messages))
	copy(out, messages)
	return out
}
