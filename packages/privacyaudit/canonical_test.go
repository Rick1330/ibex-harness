package privacyaudit

import (
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

func mustRowHash(t *testing.T, e Entry) string {
	t.Helper()
	h, err := RowHash(e)
	if err != nil {
		t.Fatal(err)
	}
	return h
}

func hashedEntry(t *testing.T, e Entry) Entry {
	t.Helper()
	e.RowHash = mustRowHash(t, e)
	return e
}

func fixedOrg() uuid.UUID {
	return uuid.MustParse("11111111-1111-1111-1111-111111111111")
}

func fixedTS() time.Time {
	return time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
}

type baseEntryOpts struct {
	org     uuid.UUID
	seq     int64
	prev    string
	action  string
	payload json.RawMessage
	fields  []string
	actor   *uuid.UUID
	ts      time.Time
}

func baseEntry(o baseEntryOpts) Entry {
	if o.org == uuid.Nil {
		o.org = fixedOrg()
	}
	if o.prev == "" {
		o.prev = GenesisPrevHash
	}
	if o.action == "" {
		o.action = "a"
	}
	if o.payload == nil {
		o.payload = json.RawMessage(`{}`)
	}
	if o.ts.IsZero() {
		o.ts = fixedTS()
	}
	if o.seq == 0 {
		o.seq = 1
	}
	return Entry{
		OrgID: o.org, Seq: o.seq, PrevHash: o.prev, ActorUserID: o.actor,
		Action: o.action, Fields: o.fields, Payload: o.payload, CreatedAt: o.ts,
	}
}

func assertCanonicalPayload(t *testing.T, raw, want string) {
	t.Helper()
	got, err := CanonicalPayload(json.RawMessage(raw))
	if err != nil {
		t.Fatal(err)
	}
	if got != want {
		t.Fatalf("got %s want %s", got, want)
	}
}

func assertBreakAt(t *testing.T, err error, wantIdx int) {
	t.Helper()
	if BreakIndex(err) != wantIdx {
		t.Fatalf("want break at %d, got idx=%d err=%v", wantIdx, BreakIndex(err), err)
	}
}

func TestCanonicalPayload_SortsKeys(t *testing.T) {
	t.Parallel()
	assertCanonicalPayload(t, `{"b":1,"a":2}`, `{"a": 2, "b": 1}`)
	// PostgreSQL jsonb: shorter keys first, then bytewise (b before aa).
	assertCanonicalPayload(t, `{"aa":1,"b":2}`, `{"b": 2, "aa": 1}`)
}

func TestCanonicalPayload_EmptyMapsToObject(t *testing.T) {
	t.Parallel()
	for _, raw := range []json.RawMessage{nil, {}} {
		got, err := CanonicalPayload(raw)
		if err != nil || got != "{}" {
			t.Fatalf("raw=%q got=%q err=%v", raw, got, err)
		}
	}
}

func TestCanonicalPayload_JSONNullPreserved(t *testing.T) {
	t.Parallel()
	got, err := CanonicalPayload(json.RawMessage(`null`))
	if err != nil || got != "null" {
		t.Fatalf("got=%q err=%v", got, err)
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
	assertCanonicalPayload(t, `{"z":[{"b":1,"a":2}],"a":true}`, `{"a": true, "z": [{"a": 2, "b": 1}]}`)
}

func TestCanonicalPayload_NoHTMLEscape(t *testing.T) {
	t.Parallel()
	assertCanonicalPayload(t, `{"x":"<tag>&"}`, `{"x": "<tag>&"}`)
}

func TestCanonicalPayload_LineSeparatorLiteral(t *testing.T) {
	t.Parallel()
	// U+2028 / U+2029 must remain literal UTF-8 (PG jsonb_out); Go json escapes them.
	raw := "{\"x\":\"a\u2028b\u2029c\"}"
	want := "{\"x\": \"a\u2028b\u2029c\"}"
	assertCanonicalPayload(t, raw, want)
	e := hashedEntry(t, baseEntry(baseEntryOpts{
		payload: json.RawMessage(raw),
	}))
	canon, err := CanonicalString(e)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(canon, "\u2028") || !strings.Contains(canon, "\u2029") {
		t.Fatalf("canonical missing line separators: %s", canon)
	}
	if strings.Contains(canon, `\u2028`) || strings.Contains(canon, `\u2029`) {
		t.Fatalf("canonical escaped line separators: %s", canon)
	}
}

func TestCanonicalPayload_UseNumber(t *testing.T) {
	t.Parallel()
	assertCanonicalPayload(t, `{"n":9007199254740993}`, `{"n": 9007199254740993}`)
}

func TestCanonicalPayload_ExponentNumberDecimal(t *testing.T) {
	t.Parallel()
	// PostgreSQL jsonb stores numbers as numeric; E-notation becomes decimal text.
	assertCanonicalPayload(t, `{"reading":1.230e-5}`, `{"reading": 0.00001230}`)
	assertCanonicalPayload(t, `{"n":1.23e4}`, `{"n": 12300}`)
	assertCanonicalPayload(t, `{"n":-1.5E+2}`, `{"n": -150}`)
	assertCanonicalPayload(t, `{"n":1e-1}`, `{"n": 0.1}`)
}

func TestCanonicalPayload_RejectsHugeExponent(t *testing.T) {
	t.Parallel()
	_, err := CanonicalPayload(json.RawMessage(`{"n":1e99999}`))
	if err == nil || !strings.Contains(err.Error(), "expansion exceeds") {
		t.Fatalf("want expansion bound error, got %v", err)
	}
	_, err = CanonicalPayload(json.RawMessage(`{"n":1e-99999}`))
	if err == nil || !strings.Contains(err.Error(), "expansion exceeds") {
		t.Fatalf("want expansion bound error, got %v", err)
	}
}

func TestCanonicalString_KnownVector(t *testing.T) {
	t.Parallel()
	e := baseEntry(baseEntryOpts{})
	got, err := CanonicalString(e)
	if err != nil {
		t.Fatal(err)
	}
	want := `["11111111-1111-1111-1111-111111111111", 1, "0000000000000000000000000000000000000000000000000000000000000000", "", "a", "", "", "", "", [], "", "", "", "", "", {}, "2026-01-01T00:00:00.000000Z"]`
	if got != want {
		t.Fatalf("canon=\n%s\nwant=\n%s", got, want)
	}
	sum := sha256.Sum256([]byte(want))
	wantHash := hex.EncodeToString(sum[:])
	h := mustRowHash(t, e)
	if h != wantHash {
		t.Fatalf("hash=%s want=%s", h, wantHash)
	}
}

func TestCanonicalString_NullPayload(t *testing.T) {
	t.Parallel()
	e := baseEntry(baseEntryOpts{payload: json.RawMessage(`null`)})
	got, err := CanonicalString(e)
	if err != nil {
		t.Fatal(err)
	}
	wantSuffix := `, null, "2026-01-01T00:00:00.000000Z"]`
	if !strings.HasSuffix(got, wantSuffix) {
		t.Fatalf("expected JSON null in array, got %s", got)
	}
}

func TestCanonicalString_SortedFieldsArray(t *testing.T) {
	t.Parallel()
	e := baseEntry(baseEntryOpts{
		org: uuid.New(), fields: []string{"z", "a"},
	})
	got, err := CanonicalString(e)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, `["a", "z"]`) {
		t.Fatalf("fields not sorted JSON array: %s", got)
	}
}

func TestCanonicalString_FieldsBytewiseOrder(t *testing.T) {
	t.Parallel()
	// Bytewise / COLLATE "C": 'Z' (0x5A) before 'a' (0x61); UTF-8 ä after ASCII.
	e := baseEntry(baseEntryOpts{
		org: uuid.New(), fields: []string{"apple", "Zebra", "äppel", "Banana"},
	})
	got, err := CanonicalString(e)
	if err != nil {
		t.Fatal(err)
	}
	want := `["Banana", "Zebra", "apple", "äppel"]`
	if !strings.Contains(got, want) {
		t.Fatalf("fields not bytewise-sorted: %s want %s", got, want)
	}
}

func TestVerifyChain_DetectsForgedMiddle(t *testing.T) {
	t.Parallel()
	ts := time.Date(2026, 9, 16, 12, 0, 0, 123456000, time.UTC)
	mk := func(seq int64, prev, action string) Entry {
		return hashedEntry(t, baseEntry(baseEntryOpts{
			seq: seq, prev: prev, action: action, ts: ts,
		}))
	}
	e1 := mk(1, GenesisPrevHash, "a")
	e2 := mk(2, e1.RowHash, "b")
	e3 := mk(3, e2.RowHash, "c")
	forged := e2
	forged.Action = "forged"
	assertBreakAt(t, VerifyChain([]Entry{e1, forged, e3}), 1)
}

func TestVerifyChain_DetectsPrevHashBreak(t *testing.T) {
	t.Parallel()
	org, ts := uuid.New(), time.Now().UTC()
	e1 := hashedEntry(t, baseEntry(baseEntryOpts{org: org, ts: ts}))
	e2 := hashedEntry(t, baseEntry(baseEntryOpts{
		org: org, seq: 2, prev: "deadbeef", action: "b", ts: ts,
	}))
	assertBreakAt(t, VerifyChain([]Entry{e1, e2}), 1)
}

func TestVerifyChain_DetectsSeqGap(t *testing.T) {
	t.Parallel()
	org, ts := uuid.New(), time.Now().UTC()
	e1 := hashedEntry(t, baseEntry(baseEntryOpts{org: org, ts: ts}))
	e3 := hashedEntry(t, baseEntry(baseEntryOpts{
		org: org, seq: 3, prev: e1.RowHash, action: "c", ts: ts,
	}))
	assertBreakAt(t, VerifyChain([]Entry{e1, e3}), 1)
}

func TestVerifyChain_DetectsMissingGenesis(t *testing.T) {
	t.Parallel()
	e2 := hashedEntry(t, baseEntry(baseEntryOpts{
		org: uuid.New(), seq: 2, ts: time.Now().UTC(),
	}))
	assertBreakAt(t, VerifyChain([]Entry{e2}), 0)
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
		e := hashedEntry(t, baseEntry(baseEntryOpts{
			org: org, seq: i, prev: prev, actor: &actor,
			action: "delete.org", fields: []string{"z", "a"},
			payload: json.RawMessage(`{"k":"v"}`), ts: ts,
		}))
		entries = append(entries, e)
		prev = e.RowHash
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
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || got[0] != id {
		t.Fatalf("got=%v", got)
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
