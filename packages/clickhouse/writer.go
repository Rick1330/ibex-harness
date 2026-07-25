package clickhouse

import (
	"context"
	"sync"
	"time"
)

// Writer batches TraceRecord inserts and flushes to ClickHouse.
// Flushes when the batch reaches MaxBatchSize or FlushInterval elapses.
// Safe for concurrent Write; flush errors are logged and discarded.
type Writer struct {
	ins     Inserter
	cfg     Config
	mu      sync.Mutex
	buf     []TraceRecord
	closed  bool
	stopCh  chan struct{}
	flushCh chan struct{}
	wg      sync.WaitGroup
}

// NewWriter opens a ClickHouse connection and starts the flush loop.
func NewWriter(cfg Config) (*Writer, error) {
	cfg.ApplyDefaults()
	ins, err := OpenInserter(cfg.DSN)
	if err != nil {
		return nil, err
	}
	return newWriterWithInserter(ins, cfg), nil
}

// NewWriterWithInserter builds a Writer around an injected Inserter (tests).
func NewWriterWithInserter(ins Inserter, cfg Config) *Writer {
	cfg.ApplyDefaults()
	return newWriterWithInserter(ins, cfg)
}

func newWriterWithInserter(ins Inserter, cfg Config) *Writer {
	w := &Writer{
		ins:     ins,
		cfg:     cfg,
		buf:     make([]TraceRecord, 0, cfg.MaxBatchSize),
		stopCh:  make(chan struct{}),
		flushCh: make(chan struct{}, 1),
	}
	w.wg.Add(1)
	go w.loop()
	return w
}

// Write enqueues a TraceRecord for the next batch flush.
// Returns immediately; does not wait for the insert.
func (w *Writer) Write(record TraceRecord) error {
	if err := validateRecord(record); err != nil {
		return err
	}
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.closed {
		return ErrWriterClosed
	}
	w.enqueueLocked(record)
	if len(w.buf) >= w.cfg.MaxBatchSize {
		w.signalFlush()
	}
	return nil
}

func (w *Writer) enqueueLocked(record TraceRecord) {
	if len(w.buf) >= w.cfg.MaxBufferSize {
		drop := len(w.buf) - w.cfg.MaxBufferSize + 1
		if drop > len(w.buf) {
			drop = len(w.buf)
		}
		w.buf = w.buf[drop:]
		w.observeDropped(drop)
	}
	w.buf = append(w.buf, record)
}

// Flush forces an immediate batch insert of all queued records.
func (w *Writer) Flush(ctx context.Context) error {
	rows := w.takeBuffer()
	return w.insertRows(ctx, rows)
}

// Close stops the flush loop and drains with ShutdownFlushTimeout.
func (w *Writer) Close() error {
	ctx, cancel := context.WithTimeout(context.Background(), w.cfg.ShutdownFlushTimeout)
	defer cancel()
	return w.Shutdown(ctx)
}

// Shutdown stops the flush loop and drains remaining rows using ctx's deadline.
func (w *Writer) Shutdown(ctx context.Context) error {
	w.mu.Lock()
	if w.closed {
		w.mu.Unlock()
		return nil
	}
	w.closed = true
	close(w.stopCh)
	w.mu.Unlock()

	w.wg.Wait()
	flushErr := w.Flush(ctx)
	closeErr := w.ins.Close()
	if flushErr != nil {
		return flushErr
	}
	return closeErr
}

func (w *Writer) loop() {
	defer w.wg.Done()
	ticker := time.NewTicker(w.cfg.FlushInterval)
	defer ticker.Stop()
	for {
		select {
		case <-w.stopCh:
			return
		case <-ticker.C:
			w.flushBestEffort()
		case <-w.flushCh:
			w.flushBestEffort()
		}
	}
}

func (w *Writer) signalFlush() {
	select {
	case w.flushCh <- struct{}{}:
	default:
	}
}

func (w *Writer) flushBestEffort() {
	rows := w.takeBuffer()
	if len(rows) == 0 {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), w.cfg.FlushTimeout)
	defer cancel()
	_ = w.insertRows(ctx, rows) // best-effort: never surfaces to Write
}

func (w *Writer) takeBuffer() []TraceRecord {
	w.mu.Lock()
	defer w.mu.Unlock()
	if len(w.buf) == 0 {
		return nil
	}
	rows := w.buf
	w.buf = make([]TraceRecord, 0, w.cfg.MaxBatchSize)
	return rows
}

func (w *Writer) insertRows(ctx context.Context, rows []TraceRecord) error {
	if len(rows) == 0 {
		return nil
	}
	start := time.Now()
	err := w.ins.InsertTraces(ctx, rows)
	w.observeFlush(len(rows), time.Since(start), err)
	if err != nil {
		w.logFlushError(err, len(rows))
		return err
	}
	return nil
}

func (w *Writer) observeFlush(n int, d time.Duration, err error) {
	if w.cfg.Metrics == nil {
		return
	}
	result := "ok"
	if err != nil {
		result = "error"
	}
	w.cfg.Metrics.IncClickHouseFlush(result)
	w.cfg.Metrics.AddClickHouseFlushRows(n)
	w.cfg.Metrics.ObserveClickHouseFlushSeconds(d.Seconds())
}

func (w *Writer) observeDropped(n int) {
	if n <= 0 || w.cfg.Metrics == nil {
		return
	}
	w.cfg.Metrics.AddClickHouseDroppedRows(n)
}

func (w *Writer) logFlushError(err error, n int) {
	if w.cfg.Logger == nil {
		return
	}
	w.cfg.Logger.WarnCtx(context.Background(), "clickhouse flush failed; discarding batch",
		"error", err,
		"rows", n,
		"dsn", RedactedDSN(w.cfg.DSN),
	)
}
