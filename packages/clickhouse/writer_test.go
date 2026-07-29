package clickhouse

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	ch "github.com/ClickHouse/clickhouse-go/v2"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/google/uuid"
	"github.com/stretchr/testify/require"
)

type fakeInserter struct {
	mu       sync.Mutex
	batches  [][]TraceRecord
	errOn    int // fail the Nth InsertTraces (1-based); 0 = never
	calls    int
	closed   atomic.Bool
	insertCh chan struct{}
}

func (f *fakeInserter) InsertTraces(_ context.Context, rows []TraceRecord) error {
	f.mu.Lock()
	f.calls++
	call := f.calls
	cp := append([]TraceRecord(nil), rows...)
	f.batches = append(f.batches, cp)
	fail := f.errOn == call
	ch := f.insertCh
	f.mu.Unlock()
	if ch != nil {
		select {
		case ch <- struct{}{}:
		default:
		}
	}
	if fail {
		return errors.New("forced flush error")
	}
	return nil
}

func (f *fakeInserter) Close() error {
	f.closed.Store(true)
	return nil
}

func (f *fakeInserter) totalRows() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	n := 0
	for _, b := range f.batches {
		n += len(b)
	}
	return n
}

func sampleRecord(id string) TraceRecord {
	now := time.Now().UTC()
	return TraceRecord{
		RequestID:   id,
		OrgID:       uuid.MustParse("11111111-1111-1111-1111-111111111111"),
		AgentID:     uuid.MustParse("22222222-2222-2222-2222-222222222222"),
		Model:       "gpt-4o",
		Provider:    "openai",
		StatusCode:  200,
		IsComplete:  true,
		RequestedAt: now,
		CompletedAt: now,
	}
}

func TestUnit_Writer_WriteNonBlocking(t *testing.T) {
	t.Parallel()
	ins := &fakeInserter{insertCh: make(chan struct{}, 8)}
	w := NewWriterWithInserter(ins, Config{MaxBatchSize: 100, FlushInterval: time.Hour})
	defer func() { _ = w.Close() }()

	done := make(chan struct{})
	go func() {
		_ = w.Write(sampleRecord("r1"))
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(200 * time.Millisecond):
		t.Fatal("Write blocked")
	}
}

func TestUnit_Writer_FlushesOnBatchSize(t *testing.T) {
	t.Parallel()
	ins := &fakeInserter{insertCh: make(chan struct{}, 1)}
	w := NewWriterWithInserter(ins, Config{MaxBatchSize: 3, FlushInterval: time.Hour})
	defer func() { _ = w.Close() }()

	for i := 0; i < 3; i++ {
		if err := w.Write(sampleRecord("r")); err != nil {
			t.Fatal(err)
		}
	}
	select {
	case <-ins.insertCh:
	case <-time.After(2 * time.Second):
		t.Fatal("expected size-triggered flush")
	}
	if ins.totalRows() < 3 {
		t.Fatalf("rows=%d", ins.totalRows())
	}
}

func TestUnit_Writer_FlushesOnInterval(t *testing.T) {
	t.Parallel()
	ins := &fakeInserter{insertCh: make(chan struct{}, 1)}
	w := NewWriterWithInserter(ins, Config{MaxBatchSize: 100, FlushInterval: 30 * time.Millisecond})
	defer func() { _ = w.Close() }()

	if err := w.Write(sampleRecord("r1")); err != nil {
		t.Fatal(err)
	}
	select {
	case <-ins.insertCh:
	case <-time.After(2 * time.Second):
		t.Fatal("expected interval flush")
	}
}

func TestUnit_Writer_WriteAfterClose(t *testing.T) {
	t.Parallel()
	ins := &fakeInserter{}
	w := NewWriterWithInserter(ins, Config{MaxBatchSize: 10, FlushInterval: time.Hour})
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
	if err := w.Write(sampleRecord("r")); !errors.Is(err, ErrWriterClosed) {
		t.Fatalf("got %v", err)
	}
	if !ins.closed.Load() {
		t.Fatal("inserter not closed")
	}
}

func TestUnit_Writer_ConcurrentWrites(t *testing.T) {
	t.Parallel()
	ins := &fakeInserter{}
	w := NewWriterWithInserter(ins, Config{MaxBatchSize: 50, FlushInterval: 20 * time.Millisecond})
	defer func() { _ = w.Close() }()

	var wg sync.WaitGroup
	for i := 0; i < 40; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			_ = w.Write(sampleRecord("c"))
		}(i)
	}
	wg.Wait()
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
	if n := ins.totalRows(); n != 40 {
		t.Fatalf("rows=%d want 40", n)
	}
}

func TestUnit_Writer_DropsOldestWhenBufferFull(t *testing.T) {
	t.Parallel()
	started := make(chan struct{}, 1)
	release := make(chan struct{})
	ins := &blockingInserter{started: started, release: release}
	m := &fakeMetrics{}
	w := NewWriterWithInserter(ins, Config{
		MaxBatchSize:  3,
		MaxBufferSize: 3,
		FlushInterval: time.Hour,
		FlushTimeout:  time.Minute,
		Metrics:       m,
	})
	defer func() {
		close(release)
		_ = w.Close()
	}()

	for _, id := range []string{"a", "b", "c"} {
		if err := w.Write(sampleRecord(id)); err != nil {
			t.Fatal(err)
		}
	}
	select {
	case <-started:
	case <-time.After(2 * time.Second):
		t.Fatal("expected size flush to begin")
	}
	for _, id := range []string{"d", "e", "f", "g"} {
		if err := w.Write(sampleRecord(id)); err != nil {
			t.Fatal(err)
		}
	}
	if m.dropped < 1 {
		t.Fatalf("dropped=%d want >=1 while flush blocked", m.dropped)
	}
}

type blockingInserter struct {
	started chan struct{}
	release chan struct{}
}

func (b *blockingInserter) InsertTraces(_ context.Context, _ []TraceRecord) error {
	select {
	case b.started <- struct{}{}:
	default:
	}
	<-b.release
	return nil
}

func (b *blockingInserter) Close() error { return nil }

type fakeMetrics struct {
	dropped int
}

func (f *fakeMetrics) IncClickHouseFlush(string)             {}
func (f *fakeMetrics) AddClickHouseFlushRows(int)            {}
func (f *fakeMetrics) ObserveClickHouseFlushSeconds(float64) {}
func (f *fakeMetrics) AddClickHouseDroppedRows(n int)        { f.dropped += n }

func TestUnit_TraceRecord_NoContentFields(t *testing.T) {
	t.Parallel()
	forbidden := map[string]struct{}{
		"Prompt": {}, "Completion": {}, "Content": {}, "Messages": {},
		"PromptText": {}, "CompletionText": {}, "PromptPayload": {},
	}
	rt := reflect.TypeOf(TraceRecord{})
	for i := 0; i < rt.NumField(); i++ {
		name := rt.Field(i).Name
		if _, ok := forbidden[name]; ok {
			t.Errorf("forbidden content field: %s", name)
		}
	}
}

func TestUnit_ValidateRecord(t *testing.T) {
	t.Parallel()
	r := sampleRecord("ok")
	if err := validateRecord(r); err != nil {
		t.Fatal(err)
	}
	badOrg := sampleRecord("x")
	badOrg.OrgID = uuid.Nil
	if err := validateRecord(badOrg); !errors.Is(err, ErrInvalidRecord) {
		t.Fatalf("org: %v", err)
	}
	badReq := sampleRecord("x")
	badReq.RequestID = ""
	if err := validateRecord(badReq); !errors.Is(err, ErrInvalidRecord) {
		t.Fatalf("request_id: %v", err)
	}
	badTime := sampleRecord("x")
	badTime.RequestedAt = time.Time{}
	if err := validateRecord(badTime); !errors.Is(err, ErrInvalidRecord) {
		t.Fatalf("timestamps: %v", err)
	}
}

func TestUnit_Config_ApplyDefaults(t *testing.T) {
	t.Parallel()
	var c Config
	c.ApplyDefaults()
	if c.MaxBatchSize != 500 || c.FlushInterval != 200*time.Millisecond {
		t.Fatalf("%+v", c)
	}
	if c.FlushTimeout != 5*time.Second || c.MaxBufferSize != 2000 {
		t.Fatalf("%+v", c)
	}
	if c.ShutdownFlushTimeout != 10*time.Second {
		t.Fatalf("%+v", c)
	}
}

func TestUnit_Config_BufferFloorAtBatchSize(t *testing.T) {
	t.Parallel()
	c := Config{MaxBatchSize: 100, MaxBufferSize: 10}
	c.ApplyDefaults()
	if c.MaxBufferSize != 100 {
		t.Fatalf("buffer floor=%d want 100", c.MaxBufferSize)
	}
}

func TestUnit_Writer_ShutdownLifecycle(t *testing.T) {
	t.Parallel()
	ins := &fakeInserter{}
	w := NewWriterWithInserter(ins, Config{MaxBatchSize: 100, FlushInterval: time.Hour})
	if err := w.Write(sampleRecord("drain")); err != nil {
		t.Fatal(err)
	}
	if err := w.Shutdown(context.Background()); err != nil {
		t.Fatal(err)
	}
	if ins.totalRows() != 1 {
		t.Fatalf("drained rows=%d", ins.totalRows())
	}
	if err := w.Shutdown(context.Background()); err != nil {
		t.Fatalf("idempotent shutdown: %v", err)
	}
	if err := w.Write(sampleRecord("after")); !errors.Is(err, ErrWriterClosed) {
		t.Fatalf("write after close: %v", err)
	}
	if !ins.closed.Load() {
		t.Fatal("inserter not closed")
	}
}

func TestUnit_Writer_ShutdownFlushError(t *testing.T) {
	t.Parallel()
	ins := &fakeInserter{errOn: 1}
	w := NewWriterWithInserter(ins, Config{MaxBatchSize: 100, FlushInterval: time.Hour})
	if err := w.Write(sampleRecord("x")); err != nil {
		t.Fatal(err)
	}
	if err := w.Shutdown(context.Background()); err == nil {
		t.Fatal("expected flush error on shutdown")
	}
}

func TestUnit_Writer_ShutdownCloseError(t *testing.T) {
	t.Parallel()
	ins := &closeErrInserter{}
	w := NewWriterWithInserter(ins, Config{MaxBatchSize: 10, FlushInterval: time.Hour})
	if err := w.Shutdown(context.Background()); err == nil || !strings.Contains(err.Error(), "close fail") {
		t.Fatalf("got %v", err)
	}
}

type closeErrInserter struct{}

func (closeErrInserter) InsertTraces(context.Context, []TraceRecord) error { return nil }
func (closeErrInserter) Close() error                                      { return errors.New("close fail") }

func TestUnit_Writer_NewWriter_Success(t *testing.T) {
	prev := openConn
	t.Cleanup(func() { openConn = prev })
	openConn = func(*ch.Options) (batchConn, error) { return &fakeConn{}, nil }

	w, err := NewWriter(Config{
		DSN:           "clickhouse://default:@localhost:8123/ibex",
		MaxBatchSize:  10,
		FlushInterval: time.Hour,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
}

func TestUnit_Writer_FlushEmptyAndIdleTick(t *testing.T) {
	t.Parallel()
	ins := &fakeInserter{insertCh: make(chan struct{}, 4)}
	interval := 20 * time.Millisecond
	w := NewWriterWithInserter(ins, Config{MaxBatchSize: 10, FlushInterval: interval})
	defer func() { _ = w.Close() }()

	if err := w.Flush(context.Background()); err != nil {
		t.Fatal(err)
	}
	// Idle window: ticks may run, but empty buffer must not call InsertTraces.
	select {
	case <-ins.insertCh:
		t.Fatal("unexpected insert during empty idle window")
	case <-time.After(3 * interval):
	}
	if ins.totalRows() != 0 {
		t.Fatalf("rows=%d", ins.totalRows())
	}
}

func TestUnit_observeDropped_Guards(t *testing.T) {
	t.Parallel()
	w := &Writer{cfg: Config{}} // no loop; white-box guard coverage
	w.observeDropped(0)
	w.observeDropped(-1)
	w.observeDropped(1) // nil Metrics
	m := &trackingMetrics{}
	w.cfg.Metrics = m
	w.observeDropped(2)
	if m.droppedCount() != 2 {
		t.Fatalf("dropped=%d", m.droppedCount())
	}
}

func TestUnit_Writer_MetricsAndLoggerOnFlushError(t *testing.T) {
	t.Parallel()
	ins := &fakeInserter{errOn: 1, insertCh: make(chan struct{}, 1)}
	m := &trackingMetrics{}
	log := logger.Discard("clickhouse-test")
	w := NewWriterWithInserter(ins, Config{
		DSN:           "clickhouse://default:secret@localhost:8123/ibex",
		MaxBatchSize:  1,
		FlushInterval: time.Hour,
		Metrics:       m,
		Logger:        log,
	})
	defer func() { _ = w.Close() }()

	if err := w.Write(sampleRecord("m")); err != nil {
		t.Fatal(err)
	}
	select {
	case <-ins.insertCh:
	case <-time.After(2 * time.Second):
		t.Fatal("flush wait")
	}
	require.Eventually(t, func() bool {
		errN, _ := m.snapshot()
		return errN >= 1
	}, time.Second, 5*time.Millisecond, "flush error metric not observed")
	require.Eventually(t, func() bool {
		_, rowsN := m.snapshot()
		return rowsN >= 1
	}, time.Second, 5*time.Millisecond, "flush rows metric not observed")
}

func TestUnit_Writer_NewWriter_BadDSN(t *testing.T) {
	t.Parallel()
	_, err := NewWriter(Config{DSN: ""})
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_Writer_ValidateRejectsWrite(t *testing.T) {
	t.Parallel()
	ins := &fakeInserter{}
	w := NewWriterWithInserter(ins, Config{MaxBatchSize: 10, FlushInterval: time.Hour})
	defer func() { _ = w.Close() }()
	bad := sampleRecord("x")
	bad.AgentID = uuid.Nil
	if err := w.Write(bad); !errors.Is(err, ErrInvalidRecord) {
		t.Fatalf("got %v", err)
	}
	if ins.totalRows() != 0 {
		t.Fatal("invalid record should not enqueue")
	}
}

func TestUnit_ValidateRecord_EmptyAgent(t *testing.T) {
	t.Parallel()
	bad := sampleRecord("x")
	bad.AgentID = uuid.Nil
	if err := validateRecord(bad); !errors.Is(err, ErrInvalidRecord) {
		t.Fatalf("got %v", err)
	}
}

func TestUnit_Writer_FlushErrorDoesNotAffectWrite(t *testing.T) {
	t.Parallel()
	ins := &fakeInserter{errOn: 1, insertCh: make(chan struct{}, 2)}
	w := NewWriterWithInserter(ins, Config{MaxBatchSize: 1, FlushInterval: time.Hour})
	defer func() { _ = w.Close() }()

	if err := w.Write(sampleRecord("a")); err != nil {
		t.Fatal(err)
	}
	select {
	case <-ins.insertCh:
	case <-time.After(2 * time.Second):
		t.Fatal("flush wait")
	}
	if err := w.Write(sampleRecord("b")); err != nil {
		t.Fatalf("Write after flush error: %v", err)
	}
}

type trackingMetrics struct {
	mu                                    sync.Mutex
	flushOK, flushErr, flushRows, dropped int
}

func (m *trackingMetrics) IncClickHouseFlush(result string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if result == "ok" {
		m.flushOK++
		return
	}
	m.flushErr++
}
func (m *trackingMetrics) AddClickHouseFlushRows(n int) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.flushRows += n
}
func (m *trackingMetrics) ObserveClickHouseFlushSeconds(float64) {}
func (m *trackingMetrics) AddClickHouseDroppedRows(n int) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.dropped += n
}

func (m *trackingMetrics) snapshot() (flushErr, flushRows int) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.flushErr, m.flushRows
}

func (m *trackingMetrics) droppedCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.dropped
}
