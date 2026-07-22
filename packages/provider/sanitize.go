package provider

import (
	"regexp"
	"strings"
	"unicode"
)

const maxSafeDetailRunes = 256

var secretDetailPattern = regexp.MustCompile(`(?i)(sk-[a-z0-9]+|bearer\s+\S+|api[_-]?key\s*[:=]\s*\S+)`)

// sanitizeProviderDetail returns a client-safe detail string, or empty if unsafe.
// Never pass ProviderBody through this — only already-extracted short messages.
func sanitizeProviderDetail(msg string) string {
	msg = strings.TrimSpace(msg)
	if msg == "" {
		return ""
	}
	if secretDetailPattern.MatchString(msg) {
		return ""
	}
	var b strings.Builder
	b.Grow(len(msg))
	runes := 0
	for _, r := range msg {
		if unicode.IsControl(r) && r != '\t' {
			continue
		}
		if runes >= maxSafeDetailRunes {
			break
		}
		b.WriteRune(r)
		runes++
	}
	return strings.TrimSpace(b.String())
}
