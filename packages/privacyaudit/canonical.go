// Package privacyaudit provides hash-chain canonicalization and verification
// for ibex_core.privacy_audit_ledger (milestone 4.P.3).
//
// Canonical serialization must match ibex_core.privacy_audit_append:
//
//	org_id|seq|prev_hash|actor_user_id|action|purpose|policy_result|
//	object_type|object_id|fields(csv sorted)|approval_ref|before_hash|
//	after_hash|correlation_id|request_id|payload_canonical|created_at
//
// created_at format: YYYY-MM-DDTHH:MM:SS.USZ (UTC microseconds, matching
// PostgreSQL to_char(..., 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')).
// payload_canonical is jsonb::text (keys sorted by jsonb storage).
package privacyaudit

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
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

// CanonicalPayload returns jsonb text with object keys sorted ascending.
func CanonicalPayload(raw json.RawMessage) (string, error) {
	if len(raw) == 0 || string(raw) == "null" {
		return "{}", nil
	}
	var v any
	if err := json.Unmarshal(raw, &v); err != nil {
		return "", fmt.Errorf("privacyaudit: payload: %w", err)
	}
	sorted, err := sortJSON(v)
	if err != nil {
		return "", err
	}
	b, err := json.Marshal(sorted)
	if err != nil {
		return "", fmt.Errorf("privacyaudit: marshal payload: %w", err)
	}
	return string(b), nil
}

func sortJSON(v any) (any, error) {
	switch t := v.(type) {
	case map[string]any:
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
	case []any:
		out := make([]any, len(t))
		for i, el := range t {
			sv, err := sortJSON(el)
			if err != nil {
				return nil, err
			}
			out[i] = sv
		}
		return out, nil
	default:
		return v, nil
	}
}

// FormatCreatedAt formats created_at like PostgreSQL to_char USZ.
func FormatCreatedAt(t time.Time) string {
	return t.UTC().Format("2006-01-02T15:04:05.000000Z")
}

// CanonicalString builds the preimage for row_hash.
func CanonicalString(e Entry) (string, error) {
	fields := append([]string(nil), e.Fields...)
	sort.Strings(fields)
	payload, err := CanonicalPayload(e.Payload)
	if err != nil {
		return "", err
	}
	actor := ""
	if e.ActorUserID != nil {
		actor = e.ActorUserID.String()
	}
	parts := []string{
		e.OrgID.String(),
		fmt.Sprintf("%d", e.Seq),
		e.PrevHash,
		actor,
		e.Action,
		e.Purpose,
		e.PolicyResult,
		e.ObjectType,
		e.ObjectID,
		strings.Join(fields, ","),
		e.ApprovalRef,
		e.BeforeHash,
		e.AfterHash,
		e.CorrelationID,
		e.RequestID,
		payload,
		FormatCreatedAt(e.CreatedAt),
	}
	return strings.Join(parts, "|"), nil
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
// On failure returns *ChainBreak with Index set.
func VerifyChain(entries []Entry) error {
	var prev string
	for i, e := range entries {
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
