package session_test

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/session"
)

func TestUnit_CompleteResult_String(t *testing.T) {
	t.Parallel()
	cases := []struct {
		r    session.CompleteResult
		want string
	}{
		{session.CompleteOK, "ok"},
		{session.CompleteNoop, "noop"},
		{session.CompleteNotFound, "not_found"},
		{session.CompleteResult(99), "unknown"},
	}
	for _, tc := range cases {
		if got := tc.r.String(); got != tc.want {
			t.Fatalf("%v.String()=%q want %q", tc.r, got, tc.want)
		}
	}
}
