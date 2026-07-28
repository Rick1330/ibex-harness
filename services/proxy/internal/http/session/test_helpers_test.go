package session

import (
	"context"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
	pkgsession "github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

type memSessionStore struct {
	mu             sync.Mutex
	sessions       map[string]*pkgsession.Session
	checkpoints    []pkgsession.CheckpointParams
	getErr         error
	appendErr      error
	appendFailOnce error
	getCalls       int
	appendCalls    int
	getDelay       time.Duration
}

func newMemSessionStore() *memSessionStore {
	return &memSessionStore{sessions: map[string]*pkgsession.Session{}}
}

func (m *memSessionStore) key(org, agent uuid.UUID, ext string) string {
	return org.String() + "|" + agent.String() + "|" + ext
}

func (m *memSessionStore) GetOrCreate(_ context.Context, p pkgsession.GetOrCreateParams) (*pkgsession.Session, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.getCalls++
	if m.getDelay > 0 {
		time.Sleep(m.getDelay)
	}
	if m.getErr != nil {
		return nil, m.getErr
	}
	k := m.key(p.OrgID, p.AgentID, p.ExternalID)
	if s, ok := m.sessions[k]; ok {
		cp := *s
		return &cp, nil
	}
	s := &pkgsession.Session{
		ID: uuid.New(), OrgID: p.OrgID, AgentID: p.AgentID,
		ExternalID: &p.ExternalID, Status: pkgsession.StatusActive,
		Model: p.Model, Provider: p.Provider, TurnCount: 0,
	}
	m.sessions[k] = s
	cp := *s
	return &cp, nil
}

func (m *memSessionStore) AppendCheckpoint(_ context.Context, p pkgsession.CheckpointParams) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.appendCalls++
	if m.appendFailOnce != nil {
		err := m.appendFailOnce
		m.appendFailOnce = nil
		return err
	}
	if m.appendErr != nil {
		return m.appendErr
	}
	m.checkpoints = append(m.checkpoints, p)
	return nil
}

func (m *memSessionStore) Complete(context.Context, uuid.UUID, uuid.UUID) error { return nil }

func (m *memSessionStore) AbandonIdle(context.Context, pkgsession.AbandonIdleParams) (pkgsession.AbandonIdleResult, error) {
	return pkgsession.AbandonIdleResult{}, nil
}

func (m *memSessionStore) waitAppends(t *testing.T, n int) {
	t.Helper()
	waitUntilT(t, 2*time.Second, 5*time.Millisecond, func() bool {
		m.mu.Lock()
		defer m.mu.Unlock()
		return m.appendCalls >= n
	})
}

func (m *memSessionStore) appendCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.appendCalls
}

func waitUntilT(t *testing.T, timeout, interval time.Duration, cond func() bool) {
	t.Helper()
	require.Eventually(t, cond, timeout, interval)
}

type recordingTraceWriter struct {
	mu      sync.Mutex
	records []ibexch.TraceRecord
	err     error
	writes  atomic.Int32
}

func (r *recordingTraceWriter) Write(rec ibexch.TraceRecord) error {
	r.mu.Lock()
	r.records = append(r.records, rec)
	r.writes.Add(1)
	err := r.err
	r.mu.Unlock()
	return err
}

func (r *recordingTraceWriter) writeCount() int32 {
	return r.writes.Load()
}

func testSnapshotMeta() SnapshotMeta {
	return SnapshotMeta{
		RequestID:   "req-trace-1",
		OrgID:       uuid.MustParse("11111111-1111-4111-8111-111111111111"),
		AgentID:     uuid.MustParse("22222222-2222-4222-8222-222222222222"),
		AuthMs:      3,
		DirectiveMs: 4,
		RequestedAt: time.Now().UTC().Add(-100 * time.Millisecond),
	}
}

func testCheckpointInput() CheckpointInput {
	return CheckpointInput{
		Messages:       []llm.Message{{Role: "user", Content: "hi"}},
		CompletionText: "hello",
		Model:          "gpt-4o",
		Provider:       "openai",
		IsComplete:     true,
	}
}

func newTestCache(t *testing.T) *sessioncache.Cache {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() {
		if err := client.Close(); err != nil {
			t.Errorf("redis close: %v", err)
		}
	})
	cache, err := sessioncache.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	return cache
}
