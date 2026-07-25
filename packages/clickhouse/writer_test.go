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
	"github.com/google/uuid"
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

func TestUnit_Writer_CloseDrainsBuffer(t *testing.T) {
	t.Parallel()
	ins := &fakeInserter{}
	w := NewWriterWithInserter(ins, Config{MaxBatchSize: 100, FlushInterval: time.Hour})
	if err := w.Write(sampleRecord("drain")); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
	if ins.totalRows() != 1 {
		t.Fatalf("drained rows=%d", ins.totalRows())
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
}

func TestUnit_DSN_ProtocolHTTPOn8123(t *testing.T) {
	t.Parallel()
	opts, err := parseOptions("clickhouse://default:@localhost:8123/ibex")
	if err != nil {
		t.Fatal(err)
	}
	if opts.Protocol != ch.HTTP {
		t.Fatalf("protocol=%v want HTTP", opts.Protocol)
	}
	if opts.Auth.Database != "ibex" {
		t.Fatalf("db=%s", opts.Auth.Database)
	}
}

func TestUnit_DSN_Empty(t *testing.T) {
	t.Parallel()
	if _, err := parseOptions("  "); err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_DSN_HTTPScheme(t *testing.T) {
	t.Parallel()
	opts, err := parseOptions("http://default:@localhost:8123/ibex")
	if err != nil {
		t.Fatal(err)
	}
	if opts.Protocol != ch.HTTP {
		t.Fatalf("protocol=%v", opts.Protocol)
	}
}

func TestUnit_RedactedDSN(t *testing.T) {
	t.Parallel()
	got := RedactedDSN("clickhouse://default:secret@localhost:8123/ibex?password=also")
	if strings.Contains(got, "secret") || strings.Contains(got, "also") {
		t.Fatalf("got %q", got)
	}
	if RedactedDSN("://") == "" {
		t.Fatal("invalid dsn sentinel")
	}
}
