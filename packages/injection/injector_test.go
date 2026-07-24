package injection_test

import (
	"sync"
	"sync/atomic"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/injection"
	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestUnit_InjectSystemFirst(t *testing.T) {
	t.Parallel()
	in := multiTurnGPT4o()
	out := injection.Inject(in, "Be concise.", injection.ModeSystemFirst)
	assertLen(t, out, len(in)+1)
	assertRoleContent(t, out[0], "system", "Be concise.")
	assertRoleContent(t, out[1], "system", "You are a coding assistant.")
	assertRoleContent(t, out[2], "user", "Explain channels.")
}

func TestUnit_InjectSystemAppend(t *testing.T) {
	t.Parallel()
	in := multiTurnGPT4o()
	out := injection.Inject(in, "Follow org policy.", injection.ModeSystemAppend)
	assertLen(t, out, len(in)+1)
	assertRoleContent(t, out[0], "system", "You are a coding assistant.")
	assertRoleContent(t, out[1], "system", "Follow org policy.")
	assertRoleContent(t, out[2], "user", "Explain channels.")
}

func TestUnit_InjectSystemAppendNoSystem(t *testing.T) {
	t.Parallel()
	in := []provider.Message{{Role: "user", Content: "hi"}}
	out := injection.Inject(in, "Rule", injection.ModeSystemAppend)
	assertLen(t, out, 2)
	assertRoleContent(t, out[0], "system", "Rule")
	assertRoleContent(t, out[1], "user", "hi")
}

func TestUnit_InjectUserPrepend(t *testing.T) {
	t.Parallel()
	in := multiTurnGPT4o()
	out := injection.Inject(in, "Stay brief.", injection.ModeUserPrepend)
	assertLen(t, out, len(in))
	assertRoleContent(t, out[0], "system", "You are a coding assistant.")
	want := "[DIRECTIVE]: Stay brief.\n\nExplain channels."
	assertRoleContent(t, out[1], "user", want)
}

func TestUnit_InjectUserPrependNoUser(t *testing.T) {
	t.Parallel()
	in := []provider.Message{{Role: "system", Content: "only system"}}
	out := injection.Inject(in, "ignored", injection.ModeUserPrepend)
	assertLen(t, out, 1)
	assertRoleContent(t, out[0], "system", "only system")
}

func TestUnit_InjectEmptyDirective(t *testing.T) {
	t.Parallel()
	in := multiTurnGPT4o()
	out := injection.Inject(in, "  ", injection.ModeSystemFirst)
	assertLen(t, out, len(in))
	assertRoleContent(t, out[0], "system", "You are a coding assistant.")
}

func TestUnit_InjectEmptyNilMessages(t *testing.T) {
	t.Parallel()
	out := injection.Inject(nil, "", injection.ModeSystemFirst)
	if out != nil {
		t.Fatalf("want nil, got %#v", out)
	}
}

func TestUnit_InjectDoesNotMutateInput(t *testing.T) {
	t.Parallel()
	in := multiTurnGPT4o()
	origFirst := in[0].Content
	out := injection.Inject(in, "Directive", injection.ModeSystemFirst)
	in[0].Content = "mutated"
	if out[1].Content != origFirst {
		t.Fatalf("input mutation leaked: %q", out[1].Content)
	}
	if in[0].Content == out[0].Content {
		t.Fatal("expected distinct first elements after system_first")
	}

	in = multiTurnGPT4o()
	origUser := in[1].Content
	_ = injection.Inject(in, "Stay brief.", injection.ModeUserPrepend)
	if in[1].Content != origUser {
		t.Fatalf("user_prepend mutated input: %q", in[1].Content)
	}
}

func TestUnit_ParseModeUnknownDefaultsSystemFirst(t *testing.T) {
	t.Parallel()
	if got := injection.ParseMode(""); got != injection.ModeSystemFirst {
		t.Fatalf("empty: %q", got)
	}
	if got := injection.ParseMode("nope"); got != injection.ModeSystemFirst {
		t.Fatalf("unknown: %q", got)
	}
	out := injection.Inject(
		[]provider.Message{{Role: "user", Content: "x"}},
		"D",
		injection.InjectionMode("bogus"),
	)
	assertRoleContent(t, out[0], "system", "D")
}

func TestUnit_InjectConcurrent(t *testing.T) {
	t.Parallel()
	in := multiTurnGPT4o()
	var wg sync.WaitGroup
	var failed atomic.Bool
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			out := injection.Inject(in, "D", injection.ModeSystemFirst)
			if len(out) != len(in)+1 {
				failed.Store(true)
			}
			if out[0].Role != "system" {
				failed.Store(true)
			}
		}()
	}
	wg.Wait()
	if failed.Load() {
		t.Fatal("concurrent inject produced invalid result")
	}
}

func BenchmarkInject_SystemFirst(b *testing.B) {
	in := multiTurnGPT4o()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = injection.Inject(in, "Be safe and concise.", injection.ModeSystemFirst)
	}
}

func multiTurnGPT4o() []provider.Message {
	return []provider.Message{
		{Role: "system", Content: "You are a coding assistant."},
		{Role: "user", Content: "Explain channels."},
		{Role: "assistant", Content: "Channels synchronize goroutines."},
		{Role: "user", Content: "Show an example."},
	}
}

func assertLen(t *testing.T, got []provider.Message, want int) {
	t.Helper()
	if len(got) != want {
		t.Fatalf("len=%d want %d", len(got), want)
	}
}

func assertRoleContent(t *testing.T, got provider.Message, role, content string) {
	t.Helper()
	if got.Role != role {
		t.Fatalf("role=%q want %q", got.Role, role)
	}
	if got.Content != content {
		t.Fatalf("content=%q want %q", got.Content, content)
	}
}
