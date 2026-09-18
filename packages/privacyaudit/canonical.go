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
// Numbers use json.Decoder.UseNumber (not float64); exponent-form numbers are
// expanded to PostgreSQL numeric decimal text (e.g. 1.230e-5 → 0.00001230).
// Strings use no HTML escaping so VerifyChain matches PG jsonb::text.
// Fields are sorted bytewise (Go sort.Strings); SQL uses ORDER BY … COLLATE "C".
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
		return nil
	case bool:
		return writeJSONBool(b, t)
	case json.Number:
		return writeJSONBNumber(b, t)
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
	default:
		return errNotPrimitive
	}
}

func writeJSONBNumber(b *strings.Builder, n json.Number) error {
	s, err := formatJSONBNumber(n)
	if err != nil {
		return err
	}
	b.WriteString(s)
	return nil
}

// formatJSONBNumber emits PostgreSQL jsonb/numeric decimal text.
// Non-exponent forms keep their lexical representation; E-notation is expanded
// (e.g. 1.230e-5 → 0.00001230) to match jsonb::text.
func formatJSONBNumber(n json.Number) (string, error) {
	s := string(n)
	ei := strings.IndexAny(s, "eE")
	if ei < 0 {
		return s, nil
	}
	if ei == 0 || ei == len(s)-1 {
		return "", fmt.Errorf("privacyaudit: invalid json number %q", s)
	}
	exp, err := strconv.Atoi(s[ei+1:])
	if err != nil {
		return "", fmt.Errorf("privacyaudit: invalid json number %q: %w", s, err)
	}
	return expandScientificDecimal(s[:ei], exp)
}

func expandScientificDecimal(significand string, exp int) (string, error) {
	sign, digits, fracDigits, err := splitSignificand(significand)
	if err != nil {
		return "", err
	}
	power := exp - fracDigits
	if power >= 0 {
		if err := checkExpandedNumberLen(len(sign)+len(digits), power); err != nil {
			return "", err
		}
		return sign + digits + strings.Repeat("0", power), nil
	}
	scale := -power
	if err := checkExpandedNumberLen(len(sign)+len(digits)+1, scale); err != nil {
		return "", err
	}
	return sign + placeDecimal(digits, scale), nil
}

// maxExpandedJSONNumberLen caps E-notation expansion so untrusted exponents
// cannot OOM the verifier (PostgreSQL jsonb payloads are far smaller in practice).
const maxExpandedJSONNumberLen = 4096

func checkExpandedNumberLen(base, pad int) error {
	if pad < 0 || base < 0 || base > maxExpandedJSONNumberLen || pad > maxExpandedJSONNumberLen-base {
		return fmt.Errorf("privacyaudit: json number expansion exceeds %d digits", maxExpandedJSONNumberLen)
	}
	return nil
}

func splitSignificand(significand string) (sign, digits string, fracDigits int, err error) {
	if strings.HasPrefix(significand, "+") {
		significand = significand[1:]
	} else if strings.HasPrefix(significand, "-") {
		sign = "-"
		significand = significand[1:]
	}
	if significand == "" {
		return "", "", 0, fmt.Errorf("privacyaudit: invalid json number significand")
	}
	dot := strings.IndexByte(significand, '.')
	digits = significand
	if dot >= 0 {
		fracDigits = len(significand) - dot - 1
		digits = significand[:dot] + significand[dot+1:]
	}
	if digits == "" || !allASCIIDigits(digits) {
		return "", "", 0, fmt.Errorf("privacyaudit: invalid json number significand %q", significand)
	}
	return sign, digits, fracDigits, nil
}

func allASCIIDigits(s string) bool {
	for _, r := range s {
		if r < '0' || r > '9' {
			return false
		}
	}
	return true
}

// placeDecimal inserts a decimal point scale digits from the right of digits,
// padding with leading zeros when needed (PostgreSQL numeric_out style).
func placeDecimal(digits string, scale int) string {
	if scale <= 0 {
		return digits
	}
	if len(digits) <= scale {
		padded := make([]byte, scale+1)
		for i := range padded {
			padded[i] = '0'
		}
		copy(padded[len(padded)-len(digits):], digits)
		digits = string(padded)
	}
	i := len(digits) - scale
	intPart := strings.TrimLeft(digits[:i], "0")
	if intPart == "" {
		intPart = "0"
	}
	return intPart + "." + digits[i:]
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

// sortedFieldsAny orders fields bytewise (sort.Strings), matching SQL
// array_agg(x ORDER BY x COLLATE "C") in privacy_audit_append.
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
