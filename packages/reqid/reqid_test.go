package reqid_test

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/google/uuid"
)

func TestNew_returnsUUIDv7(t *testing.T) {
	id := reqid.New()
	parsed, err := uuid.Parse(id)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if parsed.Version() != 7 {
		t.Fatalf("version: %d want 7", parsed.Version())
	}
}

func TestFromContext_roundTrip(t *testing.T) {
	ctx := reqid.WithRequestID(context.Background(), "abc")
	id, ok := reqid.FromContext(ctx)
	if !ok || id != "abc" {
		t.Fatalf("got %q ok=%v", id, ok)
	}
}

func TestFromContext_missing(t *testing.T) {
	_, ok := reqid.FromContext(context.Background())
	if ok {
		t.Fatal("expected false")
	}
}

func TestResolveInbound_emptyGeneratesV7(t *testing.T) {
	assertGeneratedV7(t, reqid.ResolveInbound(""))
}

func TestResolveInbound_whitespaceGeneratesV7(t *testing.T) {
	assertGeneratedV7(t, reqid.ResolveInbound("  "))
}

func TestResolveInbound_garbageGeneratesV7(t *testing.T) {
	assertGeneratedV7(t, reqid.ResolveInbound("not-a-uuid"))
}

func TestResolveInbound_honoursV4(t *testing.T) {
	v4 := uuid.New().String()
	if got := reqid.ResolveInbound(v4); got != v4 {
		t.Fatalf("got %q want %q", got, v4)
	}
}

func TestResolveInbound_honoursV7(t *testing.T) {
	v7, err := uuid.NewV7()
	if err != nil {
		t.Fatal(err)
	}
	v7Str := v7.String()
	if got := reqid.ResolveInbound(v7Str); got != v7Str {
		t.Fatalf("got %q want %q", got, v7Str)
	}
}

func TestResolveInbound_honoursTrimmedV4(t *testing.T) {
	v4 := uuid.New().String()
	if got := reqid.ResolveInbound("  " + v4 + "  "); got != v4 {
		t.Fatalf("got %q want %q", got, v4)
	}
}

func assertGeneratedV7(t *testing.T, got string) {
	t.Helper()
	parsed, err := uuid.Parse(got)
	if err != nil {
		t.Fatalf("invalid uuid: %q", got)
	}
	if parsed.Version() != 7 {
		t.Fatalf("expected v7, got version %d", parsed.Version())
	}
}

func TestMustFromContext_panics(t *testing.T) {
	defer func() {
		if recover() == nil {
			t.Fatal("expected panic")
		}
	}()
	_ = reqid.MustFromContext(context.Background())
}

func TestMustFromContext_ok(t *testing.T) {
	ctx := reqid.WithRequestID(context.Background(), "id-1")
	if reqid.MustFromContext(ctx) != "id-1" {
		t.Fatal("unexpected id")
	}
}
