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

func TestResolveInbound(t *testing.T) {
	v4 := uuid.New().String()
	v7, err := uuid.NewV7()
	if err != nil {
		t.Fatal(err)
	}
	v7Str := v7.String()

	cases := []struct {
		name    string
		raw     string
		want    string
		checkV7 bool
	}{
		{name: "empty generates", raw: "", checkV7: true},
		{name: "whitespace generates", raw: "  ", checkV7: true},
		{name: "garbage generates", raw: "not-a-uuid", checkV7: true},
		{name: "honours v4", raw: v4, want: v4},
		{name: "honours v7", raw: v7Str, want: v7Str},
		{name: "honours trimmed v4", raw: "  " + v4 + "  ", want: v4},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := reqid.ResolveInbound(tc.raw)
			if tc.want != "" && got != tc.want {
				t.Fatalf("got %q want %q", got, tc.want)
			}
			if _, err := uuid.Parse(got); err != nil {
				t.Fatalf("invalid uuid: %q", got)
			}
			if tc.checkV7 {
				parsed, _ := uuid.Parse(got)
				if parsed.Version() != 7 {
					t.Fatalf("expected v7 generated, got version %d", parsed.Version())
				}
			}
		})
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
