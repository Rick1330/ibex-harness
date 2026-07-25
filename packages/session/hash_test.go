package session_test

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/session"
)

func TestUnit_HashMessages_Stable(t *testing.T) {
	t.Parallel()

	msgs := []session.MessageForHash{
		{Role: "user", Content: "hi"},
		{Role: "assistant", Content: "yo"},
	}

	a := session.HashMessages(msgs)
	b := session.HashMessages(msgs)

	if a != b || len(a) != 64 {
		t.Fatalf("hash=%q", a)
	}
	other := session.HashMessages([]session.MessageForHash{{Role: "user", Content: "bye"}})
	if other == a {
		t.Fatal("expected different hash")
	}
}

func TestUnit_HashText(t *testing.T) {
	t.Parallel()

	empty := session.HashText("")

	if len(empty) != 64 {
		t.Fatalf("len=%d", len(empty))
	}
	if session.HashText("a") == empty {
		t.Fatal("expected different")
	}
}
