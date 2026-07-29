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
