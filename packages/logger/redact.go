package logger

import "log/slog"

var forbiddenKeys = map[string]bool{
	"token":         true,
	"password":      true,
	"hash":          true,
	"content":       true,
	"email":         true,
	"ip":            true,
	"secret":        true,
	"key":           true,
	"credential":    true,
	"bearer":        true,
	"authorization": true,
	"access_token":  true,
	"refresh_token": true,
	"api_key":       true,
	"private_key":   true,
	"session_token": true,
}

func redactAttr(a slog.Attr) slog.Attr {
	if !forbiddenKeys[a.Key] {
		return a
	}
	return slog.String(a.Key, "[REDACTED]")
}
