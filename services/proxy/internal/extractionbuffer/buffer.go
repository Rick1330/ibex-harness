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

// Key returns session:{org_id}:{agent_id}:{external_id}:extraction_turns.
func Key(k LookupKey) string {
	return fmt.Sprintf("session:%s:%s:%s:extraction_turns",
		k.OrgID.String(), k.AgentID.String(), k.ExternalID)
}

// Buffer is a fail-open Redis list of turns for a sticky session.
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

// Append adds turns to the buffer. Empty role/content entries are dropped.
// Failures never surface as errors to callers (outcome + optional err for logs).
func (b *Buffer) Append(ctx context.Context, k LookupKey, turns []Turn) (AppendOutcome, error) {
	if b == nil || b.client == nil || k.ExternalID == "" {
		return AppendSkipped, nil
	}
	clean := sanitizeTurns(turns)
	if len(clean) == 0 {
		return AppendSkipped, nil
	}

	raw, err := b.client.Get(ctx, Key(k)).Bytes()
	existing := []Turn{}
	if err == nil {
		_ = json.Unmarshal(raw, &existing)
	} else if err != redis.Nil {
		return AppendRedisErr, err
	}

	merged, capped := mergeTurns(existing, clean)
	payload, err := json.Marshal(merged)
	if err != nil {
		return AppendRedisErr, err
	}
	if err := b.client.Set(ctx, Key(k), payload, b.ttl).Err(); err != nil {
		return AppendRedisErr, err
	}
	if capped {
		return AppendCap, nil
	}
	return AppendOK, nil
}

// Take clears and returns buffered turns (GETDEL semantics). Missing key → empty.
func (b *Buffer) Take(ctx context.Context, k LookupKey) ([]Turn, error) {
	if b == nil || b.client == nil || k.ExternalID == "" {
		return nil, nil
	}
	key := Key(k)
	raw, err := b.client.GetDel(ctx, key).Bytes()
	if err == redis.Nil {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var turns []Turn
	if err := json.Unmarshal(raw, &turns); err != nil {
		return nil, fmt.Errorf("extractionbuffer: decode: %w", err)
	}
	return turns, nil
}

func sanitizeTurns(in []Turn) []Turn {
	out := make([]Turn, 0, len(in))
	for _, t := range in {
		role := truncateRunes(t.Role, maxRoleLen)
		content := truncateRunes(t.Content, maxContentLen)
		if role == "" || content == "" || t.TurnIndex < 0 {
			continue
		}
		out = append(out, Turn{TurnIndex: t.TurnIndex, Role: role, Content: content})
	}
	return out
}

func mergeTurns(existing, add []Turn) ([]Turn, bool) {
	merged := append([]Turn{}, existing...)
	capped := false
	for _, t := range add {
		if len(merged) >= MaxTurnsPerBatch {
			capped = true
			break
		}
		trial := append(merged, t)
		if serializedBytes(trial) > MaxBatchContentBytes {
			capped = true
			break
		}
		merged = trial
	}
	return merged, capped
}

func serializedBytes(turns []Turn) int {
	b, err := json.Marshal(turns)
	if err != nil {
		return MaxBatchContentBytes + 1
	}
	return len(b)
}

func truncateRunes(s string, max int) string {
	if max <= 0 || s == "" {
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
