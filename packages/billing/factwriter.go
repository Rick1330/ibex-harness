package billing

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2"
	"github.com/ClickHouse/clickhouse-go/v2/lib/driver"
	"github.com/google/uuid"
)

const (
	usageFactInsertSQL = `INSERT INTO ibex.usage_facts (
	request_id, org_id, agent_id, provider, model,
	original_model, fallback_model, fallback_reason,
	input_tokens, output_tokens, total_tokens,
	estimated_cost_cents, rate_card_version, completeness, occurred_at
)`
	maxProviderLen       = 64
	maxModelLen          = 256
	maxFallbackReasonLen = 128
	maxRequestIDLen      = 128
	maxRateCardVerLen    = 64
	flushTimeout         = 5 * time.Second
)

var allowedCompleteness = map[string]struct{}{
	"partial":  {},
	"complete": {},
}

// UsageFact is one ibex.usage_facts row (write-time frozen estimate).
type UsageFact struct {
	RequestID          string
	OrgID              uuid.UUID
	AgentID            uuid.UUID
	Provider           string
	Model              string
	OriginalModel      *string
	FallbackModel      *string
	FallbackReason     string
	InputTokens        uint32
	OutputTokens       uint32
	TotalTokens        uint32
	EstimatedCostCents int64
	RateCardVersion    string
	Completeness       string
	OccurredAt         time.Time
}

// UsageFactConfig configures the batch writer.
type UsageFactConfig struct {
	DSN                  string
	MaxBatchSize         int
	MaxBufferSize        int
	FlushInterval        time.Duration
	ShutdownFlushTimeout time.Duration
}

func (c *UsageFactConfig) ApplyDefaults() {
	if c.MaxBatchSize <= 0 {
		c.MaxBatchSize = 100
	}
	if c.MaxBufferSize <= 0 {
		c.MaxBufferSize = 10000
	}
	if c.FlushInterval <= 0 {
		c.FlushInterval = time.Second
	}
	if c.ShutdownFlushTimeout <= 0 {
		c.ShutdownFlushTimeout = 5 * time.Second
	}
}

// UsageFactInserter inserts usage fact batches.
type UsageFactInserter interface {
	InsertUsageFacts(ctx context.Context, rows []UsageFact) error
	Close() error
}

// UsageFactWriter batches UsageFact inserts and flushes to ClickHouse (fail-open).
type UsageFactWriter struct {
	ins     UsageFactInserter
	cfg     UsageFactConfig
	mu      sync.Mutex
	buf     []UsageFact
	closed  bool
	stopCh  chan struct{}
	flushCh chan struct{}
	wg      sync.WaitGroup
	onDrop  func(n int)
	onFlush func(n int, d time.Duration, err error)
}

// NewUsageFactWriter dials ClickHouse and starts the flush loop.
func NewUsageFactWriter(cfg UsageFactConfig) (*UsageFactWriter, error) {
	cfg.ApplyDefaults()
	ins, err := openUsageFactInserter(cfg.DSN)
	if err != nil {
		return nil, err
	}
	return newUsageFactWriter(ins, cfg), nil
}

// NewUsageFactWriterWithInserter builds a writer around an injected inserter.
func NewUsageFactWriterWithInserter(ins UsageFactInserter, cfg UsageFactConfig) *UsageFactWriter {
	cfg.ApplyDefaults()
	return newUsageFactWriter(ins, cfg)
}

func newUsageFactWriter(ins UsageFactInserter, cfg UsageFactConfig) *UsageFactWriter {
	w := &UsageFactWriter{
		ins:     ins,
		cfg:     cfg,
		buf:     make([]UsageFact, 0, cfg.MaxBatchSize),
		stopCh:  make(chan struct{}),
		flushCh: make(chan struct{}, 1),
	}
	w.wg.Add(1)
	go w.loop()
	return w
}

// Write enqueues a fact for the next batch flush (non-blocking).
func (w *UsageFactWriter) Write(fact UsageFact) error {
	if err := validateUsageFact(fact); err != nil {
		return err
	}
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.closed {
		return fmt.Errorf("billing: usage fact writer closed")
	}
	if len(w.buf) >= w.cfg.MaxBufferSize {
		w.buf = w.buf[1:]
		if w.onDrop != nil {
			w.onDrop(1)
		}
	}
	w.buf = append(w.buf, fact)
	if len(w.buf) >= w.cfg.MaxBatchSize {
		select {
		case w.flushCh <- struct{}{}:
		default:
		}
	}
	return nil
}

// Flush forces an immediate batch insert. On failure, rows are restored to the buffer.
func (w *UsageFactWriter) Flush(ctx context.Context) error {
	rows := w.takeBuffer()
	if len(rows) == 0 {
		return nil
	}
	err := w.insertRows(ctx, rows)
	if err != nil {
		w.requeueFront(rows)
		return err
	}
	return nil
}

// Close stops the flush loop and drains remaining rows.
func (w *UsageFactWriter) Close() error {
	ctx, cancel := context.WithTimeout(context.Background(), w.cfg.ShutdownFlushTimeout)
	defer cancel()
	return w.Shutdown(ctx)
}

// Shutdown stops the flush loop using ctx's deadline and closes the inserter.
func (w *UsageFactWriter) Shutdown(ctx context.Context) error {
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
	return errors.Join(flushErr, closeErr)
}

func (w *UsageFactWriter) loop() {
	defer w.wg.Done()
	ticker := time.NewTicker(w.cfg.FlushInterval)
	defer ticker.Stop()
	for {
		select {
		case <-w.stopCh:
			return
		case <-ticker.C:
			w.flushOnce()
		case <-w.flushCh:
			w.flushOnce()
		}
	}
}

func (w *UsageFactWriter) flushOnce() {
	select {
	case <-w.stopCh:
		return
	default:
	}
	ctx, cancel := context.WithTimeout(context.Background(), flushTimeout)
	defer cancel()
	done := make(chan struct{})
	go func() {
		defer close(done)
		// No automatic retry after uncertain Send outcomes: usage_facts has no
		// idempotency key, so retrying could double-count spend. Failed rows are
		// restored to the buffer and retried on the next tick / flush signal.
		_ = w.Flush(ctx)
	}()
	select {
	case <-done:
	case <-w.stopCh:
		cancel()
		<-done
	case <-ctx.Done():
		<-done
	}
}

func (w *UsageFactWriter) takeBuffer() []UsageFact {
	w.mu.Lock()
	defer w.mu.Unlock()
	if len(w.buf) == 0 {
		return nil
	}
	rows := w.buf
	w.buf = make([]UsageFact, 0, w.cfg.MaxBatchSize)
	return rows
}

func (w *UsageFactWriter) requeueFront(rows []UsageFact) {
	if len(rows) == 0 {
		return
	}
	w.mu.Lock()
	defer w.mu.Unlock()
	// Prefer keeping restored (older) rows; drop newer concurrent writes first.
	combined := make([]UsageFact, 0, len(rows)+len(w.buf))
	combined = append(combined, rows...)
	combined = append(combined, w.buf...)
	if len(combined) > w.cfg.MaxBufferSize {
		drop := len(combined) - w.cfg.MaxBufferSize
		combined = combined[:len(combined)-drop]
		if w.onDrop != nil {
			w.onDrop(drop)
		}
	}
	w.buf = combined
}

func (w *UsageFactWriter) insertRows(ctx context.Context, rows []UsageFact) error {
	if len(rows) == 0 {
		return nil
	}
	start := time.Now()
	err := w.ins.InsertUsageFacts(ctx, rows)
	if w.onFlush != nil {
		w.onFlush(len(rows), time.Since(start), err)
	}
	return err
}

func validateUsageFact(f UsageFact) error {
	if err := validateFactIDs(f); err != nil {
		return err
	}
	if err := validateFactModels(f); err != nil {
		return err
	}
	return validateFactTokens(f)
}

func validateFactIDs(f UsageFact) error {
	if f.RequestID == "" || f.OrgID == uuid.Nil || f.AgentID == uuid.Nil {
		return fmt.Errorf("billing: usage fact missing required ids")
	}
	if len(f.RequestID) > maxRequestIDLen {
		return fmt.Errorf("billing: request_id too long")
	}
	if f.OccurredAt.IsZero() {
		return fmt.Errorf("billing: usage fact missing occurred_at")
	}
	return nil
}

func validateFactModels(f UsageFact) error {
	if strings.TrimSpace(f.Provider) == "" || strings.TrimSpace(f.Model) == "" {
		return fmt.Errorf("billing: provider and model are required")
	}
	if len(f.Provider) > maxProviderLen || len(f.Model) > maxModelLen {
		return fmt.Errorf("billing: provider or model exceeds max length")
	}
	if len(f.FallbackReason) > maxFallbackReasonLen {
		return fmt.Errorf("billing: fallback_reason too long")
	}
	if err := validateOptionalModelLen(f.OriginalModel, "original_model"); err != nil {
		return err
	}
	if err := validateOptionalModelLen(f.FallbackModel, "fallback_model"); err != nil {
		return err
	}
	return validateRateCardVersion(f.RateCardVersion)
}

func validateRateCardVersion(ver string) error {
	if ver == "" || len(ver) > maxRateCardVerLen {
		return fmt.Errorf("billing: usage fact missing or invalid rate_card_version")
	}
	return nil
}

func validateOptionalModelLen(model *string, field string) error {
	if model != nil && len(*model) > maxModelLen {
		return fmt.Errorf("billing: %s too long", field)
	}
	return nil
}

func validateFactTokens(f UsageFact) error {
	completeness := f.Completeness
	if completeness == "" {
		completeness = "partial"
	}
	if _, ok := allowedCompleteness[completeness]; !ok {
		return fmt.Errorf("billing: invalid completeness %q", f.Completeness)
	}
	sum, ok := addUint32Checked(f.InputTokens, f.OutputTokens)
	if !ok {
		return fmt.Errorf("billing: token sum overflow")
	}
	if f.TotalTokens != sum {
		return fmt.Errorf("billing: total_tokens must equal input+output")
	}
	if f.EstimatedCostCents < 0 {
		return fmt.Errorf("billing: estimated_cost_cents must be non-negative")
	}
	return nil
}

func addUint32Checked(a, b uint32) (uint32, bool) {
	sum := uint64(a) + uint64(b)
	if sum > uint64(^uint32(0)) {
		return 0, false
	}
	return uint32(sum), true
}

type chUsageFactInserter struct {
	conn driver.Conn
}

func openUsageFactInserter(dsn string) (UsageFactInserter, error) {
	opts, err := clickhouse.ParseDSN(dsn)
	if err != nil {
		return nil, fmt.Errorf("billing: parse dsn: %w", err)
	}
	conn, err := clickhouse.Open(opts)
	if err != nil {
		return nil, fmt.Errorf("billing: open: %w", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := conn.Ping(ctx); err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("billing: ping: %w", err)
	}
	return &chUsageFactInserter{conn: conn}, nil
}

func (c *chUsageFactInserter) InsertUsageFacts(ctx context.Context, rows []UsageFact) error {
	if len(rows) == 0 {
		return nil
	}
	batch, err := c.conn.PrepareBatch(ctx, usageFactInsertSQL)
	if err != nil {
		return fmt.Errorf("prepare batch: %w", err)
	}
	for i := range rows {
		r := rows[i]
		completeness := r.Completeness
		if completeness == "" {
			completeness = "partial"
		}
		if err := batch.Append(
			r.RequestID, r.OrgID, r.AgentID, r.Provider, r.Model,
			r.OriginalModel, r.FallbackModel, r.FallbackReason,
			r.InputTokens, r.OutputTokens, r.TotalTokens,
			r.EstimatedCostCents, r.RateCardVersion, completeness, r.OccurredAt,
		); err != nil {
			return err
		}
	}
	return batch.Send()
}

func (c *chUsageFactInserter) Close() error {
	return c.conn.Close()
}
