package privacyaudit

import (
	"database/sql"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestCanonicalPayload_SortsKeys(t *testing.T) {
	t.Parallel()
	got, err := CanonicalPayload(json.RawMessage(`{"b":1,"a":2}`))
	if err != nil {
		t.Fatal(err)
	}
	if got != `{"a":2,"b":1}` {
		t.Fatalf("got %s", got)
	}
}

func TestCanonicalPayload_EmptyAndNull(t *testing.T) {
	t.Parallel()
	for _, raw := range []json.RawMessage{nil, {}, []byte("null")} {
		got, err := CanonicalPayload(raw)
		if err != nil || got != "{}" {
			t.Fatalf("raw=%q got=%q err=%v", raw, got, err)
		}
	}
}

func TestCanonicalPayload_InvalidJSON(t *testing.T) {
	t.Parallel()
	_, err := CanonicalPayload(json.RawMessage(`{`))
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestCanonicalPayload_NestedAndArray(t *testing.T) {
	t.Parallel()
	got, err := CanonicalPayload(json.RawMessage(`{"z":[{"b":1,"a":2}],"a":true}`))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(got, `{"a":true`) {
		t.Fatalf("got %s", got)
	}
}

func TestVerifyChain_DetectsForgedMiddle(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	ts := time.Date(2026, 9, 16, 12, 0, 0, 123456000, time.UTC)
	mk := func(seq int64, prev, action string) Entry {
		e := Entry{
			OrgID: org, Seq: seq, PrevHash: prev, Action: action,
			Payload: json.RawMessage(`{}`), CreatedAt: ts,
		}
		h, err := RowHash(e)
		if err != nil {
			t.Fatal(err)
		}
		e.RowHash = h
		return e
	}
	e1 := mk(1, GenesisPrevHash, "a")
	e2 := mk(2, e1.RowHash, "b")
	e3 := mk(3, e2.RowHash, "c")
	forged := e2
	forged.Action = "forged"
	err := VerifyChain([]Entry{e1, forged, e3})
	if BreakIndex(err) != 1 {
		t.Fatalf("want break at 1, got idx=%d err=%v", BreakIndex(err), err)
	}
}

func TestVerifyChain_DetectsPrevHashBreak(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	ts := time.Now().UTC()
	e1 := Entry{OrgID: org, Seq: 1, PrevHash: GenesisPrevHash, Action: "a", Payload: json.RawMessage(`{}`), CreatedAt: ts}
	h, _ := RowHash(e1)
	e1.RowHash = h
	e2 := Entry{OrgID: org, Seq: 2, PrevHash: "deadbeef", Action: "b", Payload: json.RawMessage(`{}`), CreatedAt: ts}
	h2, _ := RowHash(e2)
	e2.RowHash = h2
	err := VerifyChain([]Entry{e1, e2})
	if BreakIndex(err) != 1 {
		t.Fatalf("idx=%d err=%v", BreakIndex(err), err)
	}
}

func TestVerifyChain_EmptyOK(t *testing.T) {
	t.Parallel()
	if err := VerifyChain(nil); err != nil {
		t.Fatal(err)
	}
}

func TestVerifyChain_OK(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	ts := time.Date(2026, 1, 2, 3, 4, 5, 6000, time.UTC)
	actor := uuid.MustParse("22222222-2222-2222-2222-222222222222")
	var entries []Entry
	prev := GenesisPrevHash
	for i := int64(1); i <= 3; i++ {
		e := Entry{
			OrgID: org, Seq: i, PrevHash: prev, ActorUserID: &actor,
			Action: "delete.org", Fields: []string{"z", "a"},
			Payload: json.RawMessage(`{"k":"v"}`), CreatedAt: ts,
		}
		h, err := RowHash(e)
		if err != nil {
			t.Fatal(err)
		}
		e.RowHash = h
		entries = append(entries, e)
		prev = h
	}
	if err := VerifyChain(entries); err != nil {
		t.Fatal(err)
	}
}

func TestBreakIndex_NonChainError(t *testing.T) {
	t.Parallel()
	if BreakIndex(fmtError("x")) != -1 {
		t.Fatal("expected -1")
	}
}

type fmtError string

func (e fmtError) Error() string { return string(e) }

func TestResolveOrgs_InvalidFilter(t *testing.T) {
	t.Parallel()
	_, err := ResolveOrgs(t.Context(), nil, "not-a-uuid")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestResolveOrgs_Filter(t *testing.T) {
	t.Parallel()
	id := uuid.MustParse("33333333-3333-3333-3333-333333333333")
	got, err := ResolveOrgs(t.Context(), nil, id.String())
	if err != nil || len(got) != 1 || got[0] != id {
		t.Fatalf("got=%v err=%v", got, err)
	}
}

func TestParseOptionalUUID(t *testing.T) {
	t.Parallel()
	if parseOptionalUUID(sql.NullString{}) != nil {
		t.Fatal("expected nil")
	}
	if parseOptionalUUID(sql.NullString{String: "bad", Valid: true}) != nil {
		t.Fatal("expected nil on bad uuid")
	}
	id := uuid.MustParse("44444444-4444-4444-4444-444444444444")
	got := parseOptionalUUID(sql.NullString{String: id.String(), Valid: true})
	if got == nil || *got != id {
		t.Fatalf("got=%v", got)
	}
}

func TestChainBreak_ErrorString(t *testing.T) {
	t.Parallel()
	b := &ChainBreak{}
	if b.Error() != "privacyaudit: chain break" {
		t.Fatalf("%q", b.Error())
	}
}

func TestFormatCreatedAt_UTC(t *testing.T) {
	t.Parallel()
	ts := time.Date(2026, 9, 16, 15, 30, 45, 123456000, time.FixedZone("X", 3*3600))
	got := FormatCreatedAt(ts)
	if got != "2026-09-16T12:30:45.123456Z" {
		t.Fatalf("got %s", got)
	}
}
