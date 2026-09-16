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
package privacyaudit

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
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
	v, err := decodeJSON(raw)
	if err != nil {
		return nil, fmt.Errorf("privacyaudit: payload: %w", err)
	}
	return sortJSON(v)
}

func decodeJSON(raw []byte) (any, error) {
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

func sortJSONObject(t map[string]any) (any, error) {
	keys := make([]string, 0, len(t))
	for k := range t {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := make(map[string]any, len(keys))
	for _, k := range keys {
		sv, err := sortJSON(t[k])
		if err != nil {
			return nil, err
		}
		out[k] = sv
	}
	return out, nil
}

func sortJSONArray(t []any) (any, error) {
	out := make([]any, len(t))
	for i, el := range t {
		sv, err := sortJSON(el)
		if err != nil {
			return nil, err
		}
		out[i] = sv
	}
	return out, nil
}

// marshalJSONB encodes v like PostgreSQL jsonb::text (spaces after ':' and ',').
func marshalJSONB(v any) (string, error) {
	var b strings.Builder
	if err := writeJSONB(&b, v); err != nil {
		return "", err
	}
	return b.String(), nil
}

func writeJSONB(b *strings.Builder, v any) error {
	switch t := v.(type) {
	case nil:
		b.WriteString("null")
		return nil
	case bool:
		if t {
			b.WriteString("true")
		} else {
			b.WriteString("false")
		}
		return nil
	case json.Number:
		b.WriteString(string(t))
		return nil
	case int64:
		b.WriteString(strconv.FormatInt(t, 10))
		return nil
	case int:
		b.WriteString(strconv.Itoa(t))
		return nil
	case float64:
		b.WriteString(strconv.FormatFloat(t, 'f', -1, 64))
		return nil
	case string:
		return writeJSONString(b, t)
	case map[string]any:
		return writeJSONObject(b, t)
	case []any:
		return writeJSONArray(b, t)
	default:
		return fmt.Errorf("privacyaudit: unsupported jsonb type %T", v)
	}
}

func writeJSONString(b *strings.Builder, s string) error {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(s); err != nil {
		return fmt.Errorf("privacyaudit: marshal string: %w", err)
	}
	// Encode appends a newline.
	out := buf.Bytes()
	if len(out) > 0 && out[len(out)-1] == '\n' {
		out = out[:len(out)-1]
	}
	b.Write(out)
	return nil
}

func writeJSONObject(b *strings.Builder, m map[string]any) error {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
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
	fields := append([]string(nil), e.Fields...)
	sort.Strings(fields)
	fieldAny := make([]any, len(fields))
	for i, f := range fields {
		fieldAny[i] = f
	}
	payload, err := payloadValue(e.Payload)
	if err != nil {
		return "", err
	}
	actor := ""
	if e.ActorUserID != nil {
		actor = e.ActorUserID.String()
	}
	arr := []any{
		e.OrgID.String(),
		e.Seq,
		e.PrevHash,
		actor,
		e.Action,
		e.Purpose,
		e.PolicyResult,
		e.ObjectType,
		e.ObjectID,
		fieldAny,
		e.ApprovalRef,
		e.BeforeHash,
		e.AfterHash,
		e.CorrelationID,
		e.RequestID,
		payload,
		FormatCreatedAt(e.CreatedAt),
	}
	return marshalJSONB(arr)
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
// On failure returns *ChainBreak with Index set.
func VerifyChain(entries []Entry) error {
	var prev string
	for i, e := range entries {
		wantSeq := int64(i + 1)
		if e.Seq != wantSeq {
			return &ChainBreak{
				Index: i,
				Seq:   e.Seq,
				Err:   fmt.Errorf("privacyaudit: expected seq %d, got %d", wantSeq, e.Seq),
			}
		}
		wantPrev := GenesisPrevHash
		if i > 0 {
			wantPrev = prev
		}
		if e.PrevHash != wantPrev {
			return &ChainBreak{
				Index: i,
				Seq:   e.Seq,
				Err:   fmt.Errorf("privacyaudit: seq %d prev_hash mismatch", e.Seq),
			}
		}
		got, herr := RowHash(e)
		if herr != nil {
			return &ChainBreak{Index: i, Seq: e.Seq, Err: herr}
		}
		if got != e.RowHash {
			return &ChainBreak{
				Index: i,
				Seq:   e.Seq,
				Err:   fmt.Errorf("privacyaudit: seq %d row_hash mismatch", e.Seq),
			}
		}
		prev = e.RowHash
	}
	return nil
}

// BreakIndex returns the failing index from a VerifyChain error, or -1.
func BreakIndex(err error) int {
	if b, ok := err.(*ChainBreak); ok {
		return b.Index
	}
	return -1
}
