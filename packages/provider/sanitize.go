package provider

import (
	"regexp"
	"strings"
	"unicode"
)

const maxSafeDetailRunes = 256

// safeDetailShapes is an allowlist of validation-like upstream messages safe to
// surface as envelope detail. Anything else (including free-form / credential-
// bearing text) is dropped.
var safeDetailShapes = []*regexp.Regexp{
	regexp.MustCompile(`(?i)^invalid\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,200}$`),
	regexp.MustCompile(`(?i)^missing\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,200}$`),
	regexp.MustCompile(`(?i)^required\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,200}$`),
	regexp.MustCompile(`(?i)^unsupported\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,200}$`),
	regexp.MustCompile(`(?i)^expected\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,200}$`),
	regexp.MustCompile(`(?i)^[\p{L}\p{N} _.,:;'"()\[\]\-/+]{1,80}\smust\s(be|have|not)\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,120}$`),
	regexp.MustCompile(`(?i)^'[^']{1,64}'\sis\s(a\s)?required\b[\p{L}\p{N} _.,:;'"()\[\]\-/+]{0,120}$`),
}

// sanitizeProviderDetail returns a client-safe detail string, or empty if the
// message is not an allowlisted validation shape. Never pass ProviderBody.
func sanitizeProviderDetail(msg string) string {
	msg = strings.TrimSpace(msg)
	if msg == "" {
		return ""
	}
	cleaned := stripUnsafeRunes(msg)
	if cleaned == "" || !matchesSafeDetailShape(cleaned) {
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
