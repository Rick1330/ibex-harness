package billing

import (
	"context"
	"errors"
	"math"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2"
	"github.com/ClickHouse/clickhouse-go/v2/lib/column"
	"github.com/ClickHouse/clickhouse-go/v2/lib/driver"
	"github.com/google/uuid"
)

type fakeBatch struct {
	rows    [][]any
	appendE error
	sendE   error
	sent    bool
}

func (b *fakeBatch) Append(v ...any) error {
	if b.appendE != nil {
		return b.appendE
	}
	cp := append([]any(nil), v...)
	b.rows = append(b.rows, cp)
	return nil
}

func (b *fakeBatch) Abort() error                  { return nil }
func (b *fakeBatch) Flush() error                  { return nil }
func (b *fakeBatch) Send() error                   { b.sent = true; return b.sendE }
func (b *fakeBatch) IsSent() bool                  { return b.sent }
func (b *fakeBatch) Rows() int                     { return len(b.rows) }
func (b *fakeBatch) Columns() []column.Interface   { return nil }
func (b *fakeBatch) Column(int) driver.BatchColumn { return nil }
func (b *fakeBatch) AppendStruct(any) error        { return nil }
func (b *fakeBatch) Close() error                  { return nil }

type fakeConn struct {
	batch    *fakeBatch
	prepareE error
	pingE    error
	closed   bool
}

func (c *fakeConn) PrepareBatch(_ context.Context, _ string, _ ...driver.PrepareBatchOption) (driver.Batch, error) {
	if c.prepareE != nil {
		return nil, c.prepareE
	}
	if c.batch == nil {
		c.batch = &fakeBatch{}
	}
	return c.batch, nil
}

func (c *fakeConn) Ping(context.Context) error { return c.pingE }

func (c *fakeConn) Close() error {
	c.closed = true
	return nil
}

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

func TestUsageFactWriter_FlushWaitsBeforeShutdownClose(t *testing.T) {
	t.Parallel()
	started := make(chan struct{})
	release := make(chan struct{})
	ins := &blockingUsageFactInserter{started: started, release: release}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize: 10, MaxBufferSize: 100, FlushInterval: time.Hour,
	})
	if err := w.Write(validUsageFact()); err != nil {
		t.Fatal(err)
	}
	errCh := make(chan error, 1)
	go func() { errCh <- w.Flush(context.Background()) }()
	<-started
	done := make(chan struct{})
	go func() {
		defer close(done)
		if err := w.Shutdown(context.Background()); err != nil {
			t.Errorf("shutdown: %v", err)
		}
	}()
	select {
	case <-done:
		t.Fatal("Shutdown closed inserter while Flush still in flight")
	case <-time.After(50 * time.Millisecond):
	}
	close(release)
	if err := <-errCh; err != nil {
		t.Fatal(err)
	}
	<-done
	if ins.closeCount() != 1 {
		t.Fatalf("closes=%d want 1", ins.closeCount())
	}
	if ins.insertCount() != 1 {
		t.Fatalf("inserts=%d want 1", ins.insertCount())
	}
}

type blockingUsageFactInserter struct {
	mu        sync.Mutex
	started   chan struct{}
	release   chan struct{}
	closed    int
	inserts   int
	startOnce sync.Once
}

func (b *blockingUsageFactInserter) InsertUsageFacts(_ context.Context, _ []UsageFact) error {
	b.mu.Lock()
	b.inserts++
	b.mu.Unlock()
	b.startOnce.Do(func() { close(b.started) })
	<-b.release
	return nil
}

func (b *blockingUsageFactInserter) Close() error {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.closed++
	return nil
}

func (b *blockingUsageFactInserter) closeCount() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.closed
}

func (b *blockingUsageFactInserter) insertCount() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.inserts
}

func TestUsageFactWriter_ValidateFailures(t *testing.T) {
	t.Parallel()
	w := newValidateWriter(t)
	base := validUsageFact()
	for _, tc := range usageFactValidateCases() {
		t.Run(tc.name, func(t *testing.T) {
			err := w.Write(tc.mut(base))
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("err=%v want substring %q", err, tc.want)
			}
		})
	}
}

func TestUsageFactWriter_WriteAfterShutdown(t *testing.T) {
	t.Parallel()
	ins := &fakeUsageFactInserter{}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize: 10, MaxBufferSize: 100, FlushInterval: time.Hour,
	})
	t.Cleanup(func() { _ = w.Shutdown(context.Background()) })
	if err := w.Shutdown(context.Background()); err != nil {
		t.Fatal(err)
	}
	err := w.Write(validUsageFact())
	if err == nil || !strings.Contains(err.Error(), "closed") {
		t.Fatalf("closed write err=%v", err)
	}
}

type usageFactValidateCase struct {
	name string
	mut  func(UsageFact) UsageFact
	want string
}

func newValidateWriter(t *testing.T) *UsageFactWriter {
	t.Helper()
	ins := &fakeUsageFactInserter{}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize: 10, MaxBufferSize: 100, FlushInterval: time.Hour,
	})
	t.Cleanup(func() { _ = w.Shutdown(context.Background()) })
	return w
}

func usageFactValidateCases() []usageFactValidateCase {
	return []usageFactValidateCase{
		{
			name: "missing ids",
			mut:  func(f UsageFact) UsageFact { f.OrgID = uuid.Nil; return f },
			want: "missing required ids",
		},
		{
			name: "empty request_id",
			mut:  func(f UsageFact) UsageFact { f.RequestID = ""; return f },
			want: "missing required ids",
		},
		{
			name: "nil agent_id",
			mut:  func(f UsageFact) UsageFact { f.AgentID = uuid.Nil; return f },
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
			name: "provider too long",
			mut: func(f UsageFact) UsageFact {
				f.Provider = strings.Repeat("p", maxProviderLen+1)
				return f
			},
			want: "provider or model exceeds max length",
		},
		{
			name: "fallback model too long",
			mut: func(f UsageFact) UsageFact {
				long := strings.Repeat("m", maxModelLen+1)
				f.FallbackModel = &long
				return f
			},
			want: "fallback_model too long",
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
			name: "token sum overflow",
			mut: func(f UsageFact) UsageFact {
				f.InputTokens = math.MaxUint32
				f.OutputTokens = 1
				f.TotalTokens = 0
				return f
			},
			want: "token sum overflow",
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
}

func TestUsageFactWriter_EmptyCompletenessAcceptedAsPartial(t *testing.T) {
	t.Parallel()
	ins := &fakeUsageFactInserter{}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize: 10, MaxBufferSize: 100, FlushInterval: time.Hour,
	})
	t.Cleanup(func() { _ = w.Shutdown(context.Background()) })

	fact := validUsageFact()
	fact.Completeness = ""
	if err := w.Write(fact); err != nil {
		t.Fatal(err)
	}
	if err := w.Flush(context.Background()); err != nil {
		t.Fatal(err)
	}
	rows := ins.lastRows()
	if len(rows) != 1 {
		t.Fatalf("rows=%d", len(rows))
	}
	if rows[0].Completeness != "" {
		t.Fatalf("writer should enqueue empty completeness unchanged; got %q", rows[0].Completeness)
	}
}

func TestUsageFactWriter_BufferFullRejectsLoudly(t *testing.T) {
	t.Parallel()
	ins := &fakeUsageFactInserter{}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize:  10,
		MaxBufferSize: 1,
		FlushInterval: time.Hour,
	})
	t.Cleanup(func() { _ = w.Shutdown(context.Background()) })

	dropped := 0
	w.SetOnDrop(func(n int) { dropped += n })

	first := validUsageFact()
	first.RequestID = "keep-me"
	second := validUsageFact()
	second.RequestID = "reject-me"
	if err := w.Write(first); err != nil {
		t.Fatal(err)
	}
	err := w.Write(second)
	if err == nil || !strings.Contains(err.Error(), "buffer full") {
		t.Fatalf("second write err=%v want buffer full", err)
	}
	if dropped != 1 {
		t.Fatalf("onDrop calls=%d want 1", dropped)
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
	t.Cleanup(func() { _ = w.Shutdown(context.Background()) })
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
	t.Cleanup(func() { _ = w.Shutdown(context.Background()) })
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

func TestChUsageFactInserter_InsertUsageFacts_AppendsAndSends(t *testing.T) {
	t.Parallel()
	batch := &fakeBatch{}
	conn := &fakeConn{batch: batch}
	ins := &chUsageFactInserter{conn: conn}

	orig, fb := "gpt-4o", "claude-sonnet"
	fact := validUsageFact()
	fact.Completeness = ""
	fact.OriginalModel = &orig
	fact.FallbackModel = &fb
	fact.FallbackReason = "circuit_open"

	if err := ins.InsertUsageFacts(context.Background(), []UsageFact{fact}); err != nil {
		t.Fatal(err)
	}
	if !batch.sent {
		t.Fatal("expected Send to be called")
	}
	if len(batch.rows) != 1 {
		t.Fatalf("rows=%d", len(batch.rows))
	}
	row := batch.rows[0]
	if got, ok := row[13].(string); !ok || got != "partial" {
		t.Fatalf("completeness=%v want partial", row[13])
	}
	if row[5] != &orig {
		t.Fatalf("original_model=%v", row[5])
	}
	if row[6] != &fb {
		t.Fatalf("fallback_model=%v", row[6])
	}
}

func TestChUsageFactInserter_InsertUsageFacts_PrepareBatchError(t *testing.T) {
	t.Parallel()
	ins := &chUsageFactInserter{conn: &fakeConn{prepareE: errors.New("prep")}}
	err := ins.InsertUsageFacts(context.Background(), []UsageFact{validUsageFact()})
	if err == nil || !strings.Contains(err.Error(), "prepare") {
		t.Fatalf("got %v", err)
	}
}

func TestChUsageFactInserter_InsertUsageFacts_AppendError(t *testing.T) {
	t.Parallel()
	ins := &chUsageFactInserter{conn: &fakeConn{batch: &fakeBatch{appendE: errors.New("append failed")}}}
	err := ins.InsertUsageFacts(context.Background(), []UsageFact{validUsageFact()})
	if err == nil || !strings.Contains(err.Error(), "append") {
		t.Fatalf("got %v", err)
	}
}

func TestChUsageFactInserter_InsertUsageFacts_EmptyRowsNoop(t *testing.T) {
	t.Parallel()
	conn := &fakeConn{}
	ins := &chUsageFactInserter{conn: conn}
	if err := ins.InsertUsageFacts(context.Background(), nil); err != nil {
		t.Fatal(err)
	}
	if conn.batch != nil {
		t.Fatal("empty rows must not prepare a batch")
	}
}

func TestChUsageFactInserter_Close(t *testing.T) {
	t.Parallel()
	conn := &fakeConn{}
	ins := &chUsageFactInserter{conn: conn}
	if err := ins.Close(); err != nil {
		t.Fatal(err)
	}
	if !conn.closed {
		t.Fatal("expected conn closed")
	}
}

func TestOpenUsageFactInserter_PingFailureCloses(t *testing.T) {
	prev := openCHConn
	t.Cleanup(func() { openCHConn = prev })
	fc := &fakeConn{pingE: errors.New("down")}
	openCHConn = func(*clickhouse.Options) (usageFactConn, error) { return fc, nil }

	_, err := openUsageFactInserter("clickhouse://default:@localhost:8123/ibex")
	if err == nil {
		t.Fatal("expected ping error")
	}
	if !strings.Contains(err.Error(), "ping") {
		t.Fatalf("got %v", err)
	}
	if !fc.closed {
		t.Fatal("conn should close after ping failure")
	}
}

func TestOpenUsageFactInserter_OpenFailure(t *testing.T) {
	prev := openCHConn
	t.Cleanup(func() { openCHConn = prev })
	openCHConn = func(*clickhouse.Options) (usageFactConn, error) {
		return nil, errors.New("dial")
	}
	_, err := openUsageFactInserter("clickhouse://default:@localhost:8123/ibex")
	if err == nil || !strings.Contains(err.Error(), "open") {
		t.Fatalf("got %v", err)
	}
}

func TestOpenUsageFactInserter_ParseDSNError(t *testing.T) {
	t.Parallel()
	_, err := openUsageFactInserter("")
	if err == nil || !strings.Contains(err.Error(), "parse dsn") {
		t.Fatalf("got %v", err)
	}
}

func TestUsageFactWriter_RequeueFront_DropsNewerRowsOnOverflow(t *testing.T) {
	t.Parallel()
	started := make(chan struct{})
	release := make(chan struct{})
	ins := &blockingFailUsageFactInserter{started: started, release: release}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize: 10, MaxBufferSize: 2, FlushInterval: time.Hour,
	})
	t.Cleanup(func() { _ = w.Shutdown(context.Background()) })

	var dropMu sync.Mutex
	dropN := 0
	w.SetOnDrop(func(n int) {
		dropMu.Lock()
		dropN += n
		dropMu.Unlock()
	})

	older := []UsageFact{
		withRequestID(validUsageFact(), "old-1"),
		withRequestID(validUsageFact(), "old-2"),
	}
	for _, f := range older {
		if err := w.Write(f); err != nil {
			t.Fatal(err)
		}
	}

	errCh := make(chan error, 1)
	go func() { errCh <- w.Flush(context.Background()) }()
	<-started

	newer := []UsageFact{
		withRequestID(validUsageFact(), "new-1"),
		withRequestID(validUsageFact(), "new-2"),
	}
	for _, f := range newer {
		if err := w.Write(f); err != nil {
			t.Fatal(err)
		}
	}
	close(release)

	if err := <-errCh; err == nil {
		t.Fatal("expected flush error")
	}
	dropMu.Lock()
	gotDrop := dropN
	dropMu.Unlock()
	if gotDrop != 2 {
		t.Fatalf("onDrop=%d want 2", gotDrop)
	}

	if err := w.Flush(context.Background()); err != nil {
		t.Fatal(err)
	}
	rows := ins.lastRows()
	if len(rows) != 2 {
		t.Fatalf("kept rows=%d want 2 older", len(rows))
	}
	if rows[0].RequestID != "old-1" || rows[1].RequestID != "old-2" {
		t.Fatalf("kept=%v,%v want old-1,old-2", rows[0].RequestID, rows[1].RequestID)
	}
}

func TestUsageFactWriter_Write_TriggersFlushAtMaxBatchSize(t *testing.T) {
	t.Parallel()
	started := make(chan struct{}, 1)
	ins := &signalingUsageFactInserter{started: started}
	w := NewUsageFactWriterWithInserter(ins, UsageFactConfig{
		MaxBatchSize: 2, MaxBufferSize: 100, FlushInterval: time.Hour,
	})
	t.Cleanup(func() { _ = w.Shutdown(context.Background()) })

	if err := w.Write(withRequestID(validUsageFact(), "a")); err != nil {
		t.Fatal(err)
	}
	select {
	case <-started:
		t.Fatal("flush must not run before MaxBatchSize")
	default:
	}
	if err := w.Write(withRequestID(validUsageFact(), "b")); err != nil {
		t.Fatal(err)
	}
	select {
	case <-started:
	case <-time.After(2 * time.Second):
		t.Fatal("expected flush after MaxBatchSize")
	}
	if ins.callCount() < 1 {
		t.Fatal("expected insert call")
	}
}

func withRequestID(f UsageFact, id string) UsageFact {
	f.RequestID = id
	return f
}

type blockingFailUsageFactInserter struct {
	mu        sync.Mutex
	started   chan struct{}
	release   chan struct{}
	calls     [][]UsageFact
	startOnce sync.Once
}

func (b *blockingFailUsageFactInserter) InsertUsageFacts(_ context.Context, rows []UsageFact) error {
	b.mu.Lock()
	cp := make([]UsageFact, len(rows))
	copy(cp, rows)
	b.calls = append(b.calls, cp)
	n := len(b.calls)
	b.mu.Unlock()

	if n == 1 {
		b.startOnce.Do(func() { close(b.started) })
		<-b.release
		return errors.New("clickhouse down")
	}
	return nil
}

func (b *blockingFailUsageFactInserter) Close() error { return nil }

func (b *blockingFailUsageFactInserter) lastRows() []UsageFact {
	b.mu.Lock()
	defer b.mu.Unlock()
	if len(b.calls) == 0 {
		return nil
	}
	return b.calls[len(b.calls)-1]
}

type signalingUsageFactInserter struct {
	mu      sync.Mutex
	calls   int
	started chan struct{}
}

func (s *signalingUsageFactInserter) InsertUsageFacts(_ context.Context, _ []UsageFact) error {
	s.mu.Lock()
	s.calls++
	s.mu.Unlock()
	select {
	case s.started <- struct{}{}:
	default:
	}
	return nil
}

func (s *signalingUsageFactInserter) Close() error { return nil }

func (s *signalingUsageFactInserter) callCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.calls
}
