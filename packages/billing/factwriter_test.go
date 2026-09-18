package billing

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
)

type fakeUsageFactInserter struct {
	mu     sync.Mutex
	calls  [][]UsageFact
	closed int
	err    error
}

func (f *fakeUsageFactInserter) InsertUsageFacts(_ context.Context, rows []UsageFact) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	cp := make([]UsageFact, len(rows))
	copy(cp, rows)
	f.calls = append(f.calls, cp)
	return f.err
}

func (f *fakeUsageFactInserter) Close() error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.closed++
	return nil
}

func (f *fakeUsageFactInserter) callCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return len(f.calls)
}

func (f *fakeUsageFactInserter) lastRows() []UsageFact {
	f.mu.Lock()
	defer f.mu.Unlock()
	if len(f.calls) == 0 {
		return nil
	}
	return f.calls[len(f.calls)-1]
}

func (f *fakeUsageFactInserter) closeCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.closed
}

func validUsageFact() UsageFact {
	return UsageFact{
		RequestID:          "req-1",
		OrgID:              uuid.New(),
		AgentID:            uuid.New(),
		Provider:           "openai",
		Model:              "gpt-4o",
		InputTokens:        10,
		OutputTokens:       5,
		TotalTokens:        15,
		EstimatedCostCents: 1,
		RateCardVersion:    "1",
		Completeness:       "complete",
		OccurredAt:         time.Now().UTC(),
	}
}

func TestUsageFactConfig_ApplyDefaults(t *testing.T) {
	t.Parallel()
	var cfg UsageFactConfig
	cfg.ApplyDefaults()
	if cfg.MaxBatchSize != 100 {
		t.Fatalf("MaxBatchSize=%d", cfg.MaxBatchSize)
	}
	if cfg.MaxBufferSize != 10000 {
		t.Fatalf("MaxBufferSize=%d", cfg.MaxBufferSize)
	}
	if cfg.FlushInterval != time.Second {
		t.Fatalf("FlushInterval=%v", cfg.FlushInterval)
	}
	if cfg.ShutdownFlushTimeout != 5*time.Second {
		t.Fatalf("ShutdownFlushTimeout=%v", cfg.ShutdownFlushTimeout)
	}

	cfg = UsageFactConfig{
		MaxBatchSize: 7, MaxBufferSize: 9,
		FlushInterval: 2 * time.Second, ShutdownFlushTimeout: 3 * time.Second,
	}
	cfg.ApplyDefaults()
	if cfg.MaxBatchSize != 7 || cfg.MaxBufferSize != 9 {
		t.Fatalf("non-zero defaults overwritten: %+v", cfg)
	}
}

func TestNewUsageFactWriterWithInserter_WriteFlushShutdown(t *testing.T) {
	t.Parallel()
	ins := &fakeUsageFactInserter{}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize:  10,
		MaxBufferSize: 100,
		FlushInterval: time.Hour,
	})
	fact := validUsageFact()
	if err := w.Write(fact); err != nil {
		t.Fatal(err)
	}
	if err := w.Flush(context.Background()); err != nil {
		t.Fatal(err)
	}
	if ins.callCount() != 1 {
		t.Fatalf("inserts=%d want 1", ins.callCount())
	}
	got := ins.lastRows()
	if len(got) != 1 || got[0].RequestID != fact.RequestID {
		t.Fatalf("rows=%+v", got)
	}
	if err := w.Shutdown(context.Background()); err != nil {
		t.Fatal(err)
	}
	if ins.closeCount() != 1 {
		t.Fatalf("closes=%d want 1", ins.closeCount())
	}
}

func TestUsageFactWriter_ValidateFailures(t *testing.T) {
	t.Parallel()
	ins := &fakeUsageFactInserter{}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize:  10,
		MaxBufferSize: 100,
		FlushInterval: time.Hour,
	})
	t.Cleanup(func() { _ = w.Shutdown(context.Background()) })

	base := validUsageFact()
	cases := []struct {
		name string
		mut  func(UsageFact) UsageFact
		want string
	}{
		{
			name: "missing ids",
			mut:  func(f UsageFact) UsageFact { f.OrgID = uuid.Nil; return f },
			want: "missing required ids",
		},
		{
			name: "long request_id",
			mut: func(f UsageFact) UsageFact {
				f.RequestID = strings.Repeat("a", maxRequestIDLen+1)
				return f
			},
			want: "request_id too long",
		},
		{
			name: "zero occurred_at",
			mut:  func(f UsageFact) UsageFact { f.OccurredAt = time.Time{}; return f },
			want: "missing occurred_at",
		},
		{
			name: "missing provider",
			mut:  func(f UsageFact) UsageFact { f.Provider = "  "; return f },
			want: "provider and model are required",
		},
		{
			name: "missing model",
			mut:  func(f UsageFact) UsageFact { f.Model = ""; return f },
			want: "provider and model are required",
		},
		{
			name: "long fallback_reason",
			mut: func(f UsageFact) UsageFact {
				f.FallbackReason = strings.Repeat("x", maxFallbackReasonLen+1)
				return f
			},
			want: "fallback_reason too long",
		},
		{
			name: "bad completeness",
			mut:  func(f UsageFact) UsageFact { f.Completeness = "bogus"; return f },
			want: "invalid completeness",
		},
		{
			name: "token mismatch",
			mut:  func(f UsageFact) UsageFact { f.TotalTokens = 1; return f },
			want: "total_tokens must equal input+output",
		},
		{
			name: "negative cost",
			mut:  func(f UsageFact) UsageFact { f.EstimatedCostCents = -1; return f },
			want: "estimated_cost_cents must be non-negative",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := w.Write(tc.mut(base))
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("err=%v want substring %q", err, tc.want)
			}
		})
	}

	if err := w.Shutdown(context.Background()); err != nil {
		t.Fatal(err)
	}
	err := w.Write(validUsageFact())
	if err == nil || !strings.Contains(err.Error(), "closed") {
		t.Fatalf("closed write err=%v", err)
	}
}

func TestUsageFactWriter_BufferDrop(t *testing.T) {
	t.Parallel()
	ins := &fakeUsageFactInserter{}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize:  10,
		MaxBufferSize: 1,
		FlushInterval: time.Hour,
	})
	t.Cleanup(func() { _ = w.Shutdown(context.Background()) })

	first := validUsageFact()
	first.RequestID = "drop-me"
	second := validUsageFact()
	second.RequestID = "keep-me"
	if err := w.Write(first); err != nil {
		t.Fatal(err)
	}
	if err := w.Write(second); err != nil {
		t.Fatal(err)
	}
	if err := w.Flush(context.Background()); err != nil {
		t.Fatal(err)
	}
	rows := ins.lastRows()
	if len(rows) != 1 || rows[0].RequestID != "keep-me" {
		t.Fatalf("rows=%+v want keep-me only", rows)
	}
}

func TestUsageFactWriter_FlushFailureRequeues(t *testing.T) {
	t.Parallel()
	ins := &fakeUsageFactInserter{err: errors.New("clickhouse down")}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize:  10,
		MaxBufferSize: 100,
		FlushInterval: time.Hour,
	})
	t.Cleanup(func() {
		ins.mu.Lock()
		ins.err = nil
		ins.mu.Unlock()
		_ = w.Shutdown(context.Background())
	})

	fact := validUsageFact()
	if err := w.Write(fact); err != nil {
		t.Fatal(err)
	}
	if err := w.Flush(context.Background()); err == nil {
		t.Fatal("expected flush error")
	}
	if ins.callCount() != 1 {
		t.Fatalf("inserts=%d", ins.callCount())
	}

	ins.mu.Lock()
	ins.err = nil
	ins.mu.Unlock()
	if err := w.Flush(context.Background()); err != nil {
		t.Fatal(err)
	}
	if ins.callCount() != 2 {
		t.Fatalf("inserts=%d want 2 after requeue", ins.callCount())
	}
	got := ins.lastRows()
	if len(got) != 1 || got[0].RequestID != fact.RequestID {
		t.Fatalf("requeued rows=%+v", got)
	}
}

func TestUsageFactWriter_DoubleShutdownIdempotent(t *testing.T) {
	t.Parallel()
	ins := &fakeUsageFactInserter{}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize:  10,
		MaxBufferSize: 100,
		FlushInterval: time.Hour,
	})
	if err := w.Shutdown(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := w.Shutdown(context.Background()); err != nil {
		t.Fatal(err)
	}
	if ins.closeCount() != 1 {
		t.Fatalf("closes=%d want 1", ins.closeCount())
	}
}

func TestNewUsageFactWriter_BadDSN(t *testing.T) {
	t.Parallel()
	_, err := NewUsageFactWriter(UsageFactConfig{DSN: "not-a-valid-clickhouse-dsn"})
	if err == nil {
		t.Fatal("expected DSN error")
	}
}

func TestUsageFactWriter_CloseDrains(t *testing.T) {
	t.Parallel()
	ins := &fakeUsageFactInserter{}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize: 100, MaxBufferSize: 100, FlushInterval: time.Hour, ShutdownFlushTimeout: time.Second,
	})
	fact := validUsageFact()
	if err := w.Write(fact); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
	if ins.callCount() != 1 {
		t.Fatalf("calls=%d want 1", ins.callCount())
	}
}

func TestUsageFactWriter_FlushIntervalTriggers(t *testing.T) {
	t.Parallel()
	ins := &fakeUsageFactInserter{}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize: 100, MaxBufferSize: 100, FlushInterval: 20 * time.Millisecond, ShutdownFlushTimeout: time.Second,
	})
	if err := w.Write(validUsageFact()); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if ins.callCount() >= 1 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	if ins.callCount() < 1 {
		t.Fatal("expected interval flush")
	}
	_ = w.Shutdown(context.Background())
}

func TestValidateOptionalModelTooLong(t *testing.T) {
	t.Parallel()
	long := strings.Repeat("m", maxModelLen+1)
	fact := validUsageFact()
	fact.OriginalModel = &long
	if err := validateUsageFact(fact); err == nil {
		t.Fatal("expected error")
	}
}

func TestValidateRateCardVersionTooLong(t *testing.T) {
	t.Parallel()
	fact := validUsageFact()
	fact.RateCardVersion = strings.Repeat("v", maxRateCardVerLen+1)
	if err := validateUsageFact(fact); err == nil {
		t.Fatal("expected error")
	}
}
