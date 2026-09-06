// Package extractionbuffer stores transient turn text for session-close extraction.
package extractionbuffer

import (
	"context"
	"encoding/json"
	"fmt"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// Mirror worker MAX_TURNS_PER_BATCH / MAX_BATCH_CONTENT_BYTES (batch.py).
const (
	MaxTurnsPerBatch     = 50
	MaxBatchContentBytes = 500_000
	maxRoleLen           = 32
	maxContentLen        = 100_000
)

// compare-and-set: only SET when the current value matches expected (empty = missing).
var appendCASLua = redis.NewScript(`
local cur = redis.call("GET", KEYS[1])
if cur == false then
  cur = ""
end
if cur ~= ARGV[1] then
  return 0
end
redis.call("SET", KEYS[1], ARGV[2], "PX", ARGV[3])
return 1
`)

// Turn is one extraction payload element (role + content + index).
type Turn struct {
	TurnIndex int    `json:"turn_index"`
	Role      string `json:"role"`
	Content   string `json:"content"`
}

// LookupKey scopes the buffer like sessioncache (org + agent + sticky external_id).
type LookupKey struct {
	OrgID      uuid.UUID
	AgentID    uuid.UUID
	ExternalID string
}

// Key returns {org_id}:session:{agent_id}:{external_id}:extraction_turns.
func Key(k LookupKey) string {
	return fmt.Sprintf("%s:session:%s:%s:extraction_turns",
		k.OrgID.String(), k.AgentID.String(), k.ExternalID)
}

// Buffer is a fail-open Redis document of turns for a sticky session.
type Buffer struct {
	client redis.UniversalClient
	ttl    time.Duration
}

// New returns a Buffer. client and positive ttl are required.
func New(client redis.UniversalClient, ttl time.Duration) (*Buffer, error) {
	if client == nil {
		return nil, fmt.Errorf("extractionbuffer: redis client is required")
	}
	if ttl <= 0 {
		return nil, fmt.Errorf("extractionbuffer: ttl must be > 0")
	}
	return &Buffer{client: client, ttl: ttl}, nil
}

// AppendOutcome describes a fail-open append attempt.
type AppendOutcome string

const (
	AppendOK       AppendOutcome = "ok"
	AppendSkipped  AppendOutcome = "skipped"
	AppendCap      AppendOutcome = "cap"
	AppendRedisErr AppendOutcome = "redis_error"
)

func (b *Buffer) usable(k LookupKey) bool {
	return b != nil && b.client != nil && k.ExternalID != ""
}

// Append adds turns to the buffer. Empty role/content entries are dropped.
// Concurrent appends merge via compare-and-set retries (no lost turns while ctx is live).
func (b *Buffer) Append(ctx context.Context, k LookupKey, turns []Turn) (AppendOutcome, error) {
	if !b.usable(k) {
		return AppendSkipped, nil
	}
	clean := sanitizeTurns(turns)
	if len(clean) == 0 {
		return AppendSkipped, nil
	}
	return b.appendWithCAS(ctx, Key(k), clean)
}

func (b *Buffer) appendWithCAS(ctx context.Context, key string, clean []Turn) (AppendOutcome, error) {
	ttlMs := b.ttlMillis()
	for attempt := 0; ; attempt++ {
		out, err := b.appendCASAttempt(ctx, key, clean, ttlMs, attempt)
		if err == nil {
			return out, nil
		}
		if !isCASConflict(err) {
			return AppendRedisErr, err
		}
	}
}

type casConflictError struct{}

func (casConflictError) Error() string { return "extractionbuffer: cas conflict" }

func isCASConflict(err error) bool {
	_, ok := err.(casConflictError)
	return ok
}

func (b *Buffer) appendCASAttempt(
	ctx context.Context, key string, clean []Turn, ttlMs int64, attempt int,
) (AppendOutcome, error) {
	if err := ctx.Err(); err != nil {
		return AppendRedisErr, err
	}
	out, conflict, err := b.tryAppendCAS(ctx, key, clean, ttlMs)
	if err != nil {
		return AppendRedisErr, err
	}
	if !conflict {
		return out, nil
	}
	if err := sleepCASBackoff(ctx, attempt); err != nil {
		return AppendRedisErr, err
	}
	return "", casConflictError{}
}

func (b *Buffer) ttlMillis() int64 {
	ttlMs := b.ttl.Milliseconds()
	if ttlMs < 1 {
		return 1
	}
	return ttlMs
}

type casWrite struct {
	expected string
	payload  string
	capped   bool
}

func (b *Buffer) tryAppendCAS(
	ctx context.Context, key string, clean []Turn, ttlMs int64,
) (AppendOutcome, bool, error) {
	write, err := b.prepareCASWrite(ctx, key, clean)
	if err != nil {
		return "", false, err
	}
	ok, err := appendCASLua.Run(ctx, b.client, []string{key}, write.expected, write.payload, ttlMs).Int()
	if err != nil {
		return "", false, err
	}
	if ok != 1 {
		return "", true, nil
	}
	if write.capped {
		return AppendCap, false, nil
	}
	return AppendOK, false, nil
}

func (b *Buffer) prepareCASWrite(ctx context.Context, key string, clean []Turn) (casWrite, error) {
	expected, existing, err := b.readExpected(ctx, key)
	if err != nil {
		return casWrite{}, err
	}
	merged, capped := mergeTurns(existing, clean)
	payload, err := json.Marshal(merged)
	if err != nil {
		return casWrite{}, err
	}
	return casWrite{expected: expected, payload: string(payload), capped: capped}, nil
}

func (b *Buffer) readExpected(ctx context.Context, key string) (string, []Turn, error) {
	raw, err := b.client.Get(ctx, key).Bytes()
	if err == redis.Nil {
		return "", nil, nil
	}
	if err != nil {
		return "", nil, err
	}
	var existing []Turn
	_ = json.Unmarshal(raw, &existing)
	return string(raw), existing, nil
}

func sleepCASBackoff(ctx context.Context, attempt int) error {
	n := attempt
	if n > 32 {
		n = 32
	}
	timer := time.NewTimer(time.Duration(n+1) * 50 * time.Microsecond)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

// Peek returns buffered turns without clearing the key.
func (b *Buffer) Peek(ctx context.Context, k LookupKey) ([]Turn, error) {
	return b.fetchTurns(ctx, k)
}

// Ack deletes the buffer after a successful enqueue accept.
func (b *Buffer) Ack(ctx context.Context, k LookupKey) error {
	if !b.usable(k) {
		return nil
	}
	return b.client.Del(ctx, Key(k)).Err()
}

// Take clears and returns buffered turns (GETDEL semantics). Missing key → empty.
func (b *Buffer) Take(ctx context.Context, k LookupKey) ([]Turn, error) {
	if !b.usable(k) {
		return nil, nil
	}
	raw, err := b.client.GetDel(ctx, Key(k)).Bytes()
	if err == redis.Nil {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return decodeTurns(raw)
}

func (b *Buffer) fetchTurns(ctx context.Context, k LookupKey) ([]Turn, error) {
	if !b.usable(k) {
		return nil, nil
	}
	raw, err := b.client.Get(ctx, Key(k)).Bytes()
	if err == redis.Nil {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return decodeTurns(raw)
}

func decodeTurns(raw []byte) ([]Turn, error) {
	var turns []Turn
	if err := json.Unmarshal(raw, &turns); err != nil {
		return nil, fmt.Errorf("extractionbuffer: decode: %w", err)
	}
	return turns, nil
}

func sanitizeTurns(in []Turn) []Turn {
	out := make([]Turn, 0, len(in))
	for _, t := range in {
		if turn, ok := sanitizeOne(t); ok {
			out = append(out, turn)
		}
	}
	return out
}

func sanitizeOne(t Turn) (Turn, bool) {
	role := truncateRunes(t.Role, maxRoleLen)
	content := truncateRunes(t.Content, maxContentLen)
	if !turnFieldsOK(role, content, t.TurnIndex) {
		return Turn{}, false
	}
	return Turn{TurnIndex: t.TurnIndex, Role: role, Content: content}, true
}

func turnFieldsOK(role, content string, turnIndex int) bool {
	if role == "" {
		return false
	}
	if content == "" {
		return false
	}
	return turnIndex >= 0
}

func mergeTurns(existing, add []Turn) ([]Turn, bool) {
	merged := append([]Turn{}, existing...)
	capped := false
	for _, t := range add {
		next, ok := tryAppendTurn(merged, t)
		if !ok {
			capped = true
			break
		}
		merged = next
	}
	return merged, capped
}

func tryAppendTurn(merged []Turn, t Turn) ([]Turn, bool) {
	if len(merged) >= MaxTurnsPerBatch {
		return merged, false
	}
	trial := append(merged, t)
	if serializedBytes(trial) > MaxBatchContentBytes {
		return merged, false
	}
	return trial, true
}

func serializedBytes(turns []Turn) int {
	b, err := json.Marshal(turns)
	if err != nil {
		return MaxBatchContentBytes + 1
	}
	return len(b)
}

func truncateRunes(s string, max int) string {
	if max <= 0 {
		return ""
	}
	if s == "" {
		return ""
	}
	if utf8.RuneCountInString(s) <= max {
		return s
	}
	runes := []rune(s)
	return string(runes[:max])
}

// TurnsFromChat builds user+assistant turn pairs for one durable chat TurnIndex.
func TurnsFromChat(turnIndex int, lastUser, completion string) []Turn {
	out := make([]Turn, 0, 2)
	if lastUser != "" {
		out = append(out, Turn{TurnIndex: turnIndex * 2, Role: "user", Content: lastUser})
	}
	if completion != "" {
		out = append(out, Turn{TurnIndex: turnIndex*2 + 1, Role: "assistant", Content: completion})
	}
	return out
}
