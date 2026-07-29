package http

import (
	"net/http"
	"testing"
)

func mustNewRouter(tb testing.TB, deps RouterDeps) http.Handler {
	tb.Helper()
	h, err := NewRouter(deps)
	if err != nil {
		tb.Fatalf("NewRouter: %v", err)
	}
	return h
}
