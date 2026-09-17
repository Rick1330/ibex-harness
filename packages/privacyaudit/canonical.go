// Package privacyaudit provides hash-chain canonicalization and verification
// for ibex_core.privacy_audit_ledger (milestone 4.P.3).
//
// Canonical serialization must match ibex_core.privacy_audit_append:
//
//	row_hash = sha256hex( jsonb_build_array(
//	  org_id::text, seq, prev_hash, actor, action, purpose, policy_result,
//	  object_type, object_id, fields_jsonb, approval_ref, before_hash,
//	  after_hash, correlation_id, request_id, payload_jsonb, created_at_usz
//	)::text )
//
// created_at format: YYYY-MM-DDTHH:MM:SS.USZ (UTC microseconds, matching
// PostgreSQL to_char(..., 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')).
// Payload: SQL NULL → {}; JSON null preserved as null.
// jsonb::text uses spaces after ':' and ',' (PostgreSQL jsonb_out).
//
// Numbers use json.Decoder.UseNumber (not float64) and strings use
// json.Encoder.SetEscapeHTML(false) so VerifyChain matches PG jsonb::text.
package privacyaudit

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

// GenesisPrevHash is the prev_hash for seq=1 (64 zero hex chars).
const GenesisPrevHash = "0000000000000000000000000000000000000000000000000000000000000000"

// Entry is one ledger row used for hash recomputation.
type Entry struct {
	OrgID         uuid.UUID
	Seq           int64
	PrevHash      string
	ActorUserID   *uuid.UUID
	Action        string
	Purpose       string
	PolicyResult  string
	ObjectType    string
	ObjectID      string
	Fields        []string
	ApprovalRef   string
	BeforeHash    string
	AfterHash     string
	CorrelationID string
	RequestID     string
	Payload       json.RawMessage
	CreatedAt     time.Time
	RowHash       string
}

// CanonicalPayload returns PostgreSQL jsonb::text for the payload field.
// Empty/nil raw maps to "{}". JSON null is preserved as "null".
func CanonicalPayload(raw json.RawMessage) (string, error) {
	v, err := payloadValue(raw)
	if err != nil {
		return "", err
	}
	return marshalJSONB(v)
}

func payloadValue(raw json.RawMessage) (any, error) {
	if len(raw) == 0 {
		return map[string]any{}, nil
	}
	v, err := decodeJSONNumber(raw)
	if err != nil {
		return nil, fmt.Errorf("privacyaudit: payload: %w", err)
	}
	return sortJSON(v)
}

// decodeJSONNumber decodes with UseNumber so large integers stay exact
// (float64 would lose precision vs PostgreSQL jsonb).
func decodeJSONNumber(raw []byte) (any, error) {
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	var v any
	if err := dec.Decode(&v); err != nil {
		return nil, err
	}
	return v, nil
}

func sortJSON(v any) (any, error) {
	switch t := v.(type) {
	case map[string]any:
		return sortJSONObject(t)
	case []any:
		return sortJSONArray(t)
	default:
		return v, nil
	}
}

func sortJSONObject(m map[string]any) (any, error) {
	keys := sortedMapKeys(m)
	out := make(map[string]any, len(keys))
	for _, k := range keys {
		sv, err := sortJSON(m[k])
		if err != nil {
			return nil, err
		}
		out[k] = sv
	}
	return out, nil
}

func sortJSONArray(a []any) (any, error) {
	out := make([]any, len(a))
	for i, el := range a {
		sv, err := sortJSON(el)
		if err != nil {
			return nil, err
		}
		out[i] = sv
	}
	return out, nil
}

// sortedMapKeys orders keys like PostgreSQL jsonb (length ascending, then bytewise).
func sortedMapKeys(m map[string]any) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool {
		if len(keys[i]) != len(keys[j]) {
			return len(keys[i]) < len(keys[j])
		}
		return keys[i] < keys[j]
	})
	return keys
}

// marshalJSONB encodes v like PostgreSQL jsonb::text (spaces after ':' and ',').
func marshalJSONB(v any) (string, error) {
	var b strings.Builder
	if err := writeJSONB(&b, v); err != nil {
		return "", err
	}
	return b.String(), nil
}

var errNotPrimitive = errors.New("privacyaudit: not primitive")

func writeJSONB(b *strings.Builder, v any) error {
	if err := writeJSONBPrimitive(b, v); !errors.Is(err, errNotPrimitive) {
		return err
	}
	switch t := v.(type) {
	case map[string]any:
		return writeJSONObject(b, t)
	case []any:
		return writeJSONArray(b, t)
	default:
		return fmt.Errorf("privacyaudit: unsupported jsonb type %T", v)
	}
}

func writeJSONBPrimitive(b *strings.Builder, v any) error {
	switch t := v.(type) {
	case nil:
		b.WriteString("null")
	case bool:
		return writeJSONBool(b, t)
	case json.Number:
		b.WriteString(string(t))
	case int64:
		b.WriteString(strconv.FormatInt(t, 10))
	case int:
		b.WriteString(strconv.Itoa(t))
	case float64:
		b.WriteString(strconv.FormatFloat(t, 'f', -1, 64))
	case string:
		return writeJSONString(b, t)
	default:
		return errNotPrimitive
	}
	return nil
}

func writeJSONBool(b *strings.Builder, v bool) error {
	if v {
		b.WriteString("true")
	} else {
		b.WriteString("false")
	}
	return nil
}

// writeJSONString encodes s like PostgreSQL jsonb_out: no HTML escaping,
// and U+2028 / U+2029 stay as literal UTF-8 (Go's encoding/json escapes them).
func writeJSONString(b *strings.Builder, s string) error {
	b.WriteByte('"')
	for _, r := range s {
		if err := writeJSONStringRune(b, r); err != nil {
			return err
		}
	}
	b.WriteByte('"')
	return nil
}

func writeJSONStringRune(b *strings.Builder, r rune) error {
	if esc, ok := jsonStringEscapes[r]; ok {
		b.WriteString(esc)
		return nil
	}
	if r < 0x20 {
		_, err := fmt.Fprintf(b, `\u%04x`, r)
		return err
	}
	b.WriteRune(r)
	return nil
}

var jsonStringEscapes = map[rune]string{
	'"':  `\"`,
	'\\': `\\`,
	'\b': `\b`,
	'\f': `\f`,
	'\n': `\n`,
	'\r': `\r`,
	'\t': `\t`,
}

func writeJSONObject(b *strings.Builder, m map[string]any) error {
	keys := sortedMapKeys(m)
	b.WriteByte('{')
	for i, k := range keys {
		if i > 0 {
			b.WriteString(", ")
		}
		if err := writeJSONString(b, k); err != nil {
			return err
		}
		b.WriteString(": ")
		if err := writeJSONB(b, m[k]); err != nil {
			return err
		}
	}
	b.WriteByte('}')
	return nil
}

func writeJSONArray(b *strings.Builder, a []any) error {
	b.WriteByte('[')
	for i, el := range a {
		if i > 0 {
			b.WriteString(", ")
		}
		if err := writeJSONB(b, el); err != nil {
			return err
		}
	}
	b.WriteByte(']')
	return nil
}

// FormatCreatedAt formats created_at like PostgreSQL to_char USZ.
func FormatCreatedAt(t time.Time) string {
	return t.UTC().Format("2006-01-02T15:04:05.000000Z")
}

// CanonicalString builds the jsonb_build_array(... )::text preimage for row_hash.
func CanonicalString(e Entry) (string, error) {
	payload, err := payloadValue(e.Payload)
	if err != nil {
		return "", err
	}
	return marshalJSONB(entryArray(e, payload))
}

func entryArray(e Entry, payload any) []any {
	return []any{
		e.OrgID.String(),
		e.Seq,
		e.PrevHash,
		actorString(e.ActorUserID),
		e.Action,
		e.Purpose,
		e.PolicyResult,
		e.ObjectType,
		e.ObjectID,
		sortedFieldsAny(e.Fields),
		e.ApprovalRef,
		e.BeforeHash,
		e.AfterHash,
		e.CorrelationID,
		e.RequestID,
		payload,
		FormatCreatedAt(e.CreatedAt),
	}
}

func actorString(id *uuid.UUID) string {
	if id == nil {
		return ""
	}
	return id.String()
}

func sortedFieldsAny(fields []string) []any {
	sorted := append([]string(nil), fields...)
	sort.Strings(sorted)
	out := make([]any, len(sorted))
	for i, f := range sorted {
		out[i] = f
	}
	return out
}

// RowHash computes sha256 hex of the canonical string.
func RowHash(e Entry) (string, error) {
	canon, err := CanonicalString(e)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256([]byte(canon))
	return hex.EncodeToString(sum[:]), nil
}

// ChainBreak describes the first verification failure.
type ChainBreak struct {
	Index int
	Seq   int64
	Err   error
}

func (b ChainBreak) Error() string {
	if b.Err == nil {
		return "privacyaudit: chain break"
	}
	return b.Err.Error()
}

// VerifyChain walks entries in seq order. On success returns nil.
// Requires first seq == 1 and each subsequent seq == previous+1 before hash checks.
// Row hashes are recomputed via CanonicalString (UseNumber + no HTML escape).
// On failure returns *ChainBreak with Index set.
func VerifyChain(entries []Entry) error {
	var prev string
	for i, e := range entries {
		if err := checkSeq(i, e); err != nil {
			return err
		}
		if err := checkPrevHash(i, e, prev); err != nil {
			return err
		}
		if err := checkRowHash(i, e); err != nil {
			return err
		}
		prev = e.RowHash
	}
	return nil
}

func checkSeq(i int, e Entry) error {
	wantSeq := int64(i + 1)
	if e.Seq == wantSeq {
		return nil
	}
	return &ChainBreak{
		Index: i,
		Seq:   e.Seq,
		Err:   fmt.Errorf("privacyaudit: expected seq %d, got %d", wantSeq, e.Seq),
	}
}

func checkPrevHash(i int, e Entry, prev string) error {
	wantPrev := GenesisPrevHash
	if i > 0 {
		wantPrev = prev
	}
	if e.PrevHash == wantPrev {
		return nil
	}
	return &ChainBreak{
		Index: i,
		Seq:   e.Seq,
		Err:   fmt.Errorf("privacyaudit: seq %d prev_hash mismatch", e.Seq),
	}
}

func checkRowHash(i int, e Entry) error {
	got, err := RowHash(e)
	if err != nil {
		return &ChainBreak{Index: i, Seq: e.Seq, Err: err}
	}
	if got == e.RowHash {
		return nil
	}
	return &ChainBreak{
		Index: i,
		Seq:   e.Seq,
		Err:   fmt.Errorf("privacyaudit: seq %d row_hash mismatch", e.Seq),
	}
}

// BreakIndex returns the failing index from a VerifyChain error, or -1.
func BreakIndex(err error) int {
	if b, ok := err.(*ChainBreak); ok {
		return b.Index
	}
	return -1
}
