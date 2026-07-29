package logger

import (
	"log/slog"
	"os"
)

// BootstrapError logs a structured error to stderr for use before the
// application logger is initialized. It is the only sanctioned use of
// bare slog outside packages/logger itself (see 29-ibex-packages.mdc).
func BootstrapError(msg string, err error) {
	slog.New(slog.NewJSONHandler(os.Stderr, nil)).Error(msg, "error", err)
}

// BootstrapDebug logs a structured DEBUG message to stderr for use before
// the application logger is initialized (same bootstrap exception as BootstrapError).
func BootstrapDebug(msg string, args ...any) {
	h := slog.NewJSONHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelDebug})
	slog.New(h).Debug(msg, args...)
}
