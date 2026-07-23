package provider

import (
	"regexp"
	"strings"
	"unicode"
)

const maxSafeDetailRunes = 256

// safeDetailShapes is an allowlist of validation-like upstream messages.
var safeDetailShapes = []*regexp.Regexp{
	regexp.MustCompile(`(?i)^invalid\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,200}$`),
	regexp.MustCompile(`(?i)^missing\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,200}$`),
	regexp.MustCompile(`(?i)^required\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,200}$`),
	regexp.MustCompile(`(?i)^unsupported\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,200}$`),
	regexp.MustCompile(`(?i)^expected\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,200}$`),
	regexp.MustCompile(`(?i)^[\p{L}\p{N} _.,:;'"()\[\]\-/+]{1,80}\smust\s(be|have|not)\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,120}$`),
	regexp.MustCompile(`(?i)^'[^']{1,64}'\sis\s(a\s)?required\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,120}$`),
}

// credentialReject catches secrets even when the message otherwise matches a
// validation-like allowlist shape (e.g. "Invalid API key sk-…").
var credentialReject = regexp.MustCompile(`(?i)(` +
	`sk-[a-z0-9_-]+|` +
	`bearer\s+\S+|` +
	`api[_-]?key|` +
	`password\s*[:=]|` +
	`secret\s*[:=]|` +
	`\btoken\s*[:=]|` +
	`eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+` +
	`)`)

// sanitizeProviderDetail returns a client-safe detail string, or empty if the
// message is not an allowlisted validation shape or contains credentials.
// Never pass ProviderBody.
func sanitizeProviderDetail(msg string) string {
	msg = strings.TrimSpace(msg)
	if msg == "" {
		return ""
	}
	cleaned := stripUnsafeRunes(msg)
	if cleaned == "" {
		return ""
	}
	if credentialReject.MatchString(cleaned) {
		return ""
	}
	if !matchesSafeDetailShape(cleaned) {
		return ""
	}
	return cleaned
}

func stripUnsafeRunes(msg string) string {
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

func matchesSafeDetailShape(msg string) bool {
	for _, re := range safeDetailShapes {
		if re.MatchString(msg) {
			return true
		}
	}
	return false
}
