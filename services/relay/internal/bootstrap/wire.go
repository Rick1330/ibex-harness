package bootstrap

import (
	"context"
	"database/sql"
	"fmt"
	"net/url"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox/clickhousesink"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/relay/internal/config"
	"github.com/Rick1330/ibex-harness/services/relay/internal/fence"

	// Register the lib/pq "postgres" driver used by sql.Open.
	_ "github.com/lib/pq"
)

// relayRoleName is the NOLOGIN role the daemon must assume for every pooled
// connection; the login role must be a member (deployment prerequisite).
const relayRoleName = "ibex_evidence_relay"

const (
	relayMaxOpenConns = 4
	relayMaxIdleConns = 2
)

// runtime bundles the constructed relay dependencies for the process lifetime.
type runtime struct {
	db    *sql.DB
	sink  *clickhousesink.Sink
	relay *evidenceoutbox.Relay
}

// openRuntime constructs PG (role-pinned), the ClickHouse pilot sink, the
// authoritative session fence checker, and the relay. Failures are returned
// with partial resources closed; the caller must fail closed (non-zero exit).
func openRuntime(ctx context.Context, cfg config.Config, reg *ibexmetrics.RelayRegistry) (*runtime, error) {
	db, err := openRelayDB(ctx, cfg.PostgresDSN.String(), cfg.OperationTimeout)
	if err != nil {
		return nil, err
	}
	checker, err := fence.NewSessionFenceChecker(db, reg)
	if err != nil {
		_ = db.Close()
		return nil, err
	}
	sink, err := clickhousesink.Open(ctx, cfg.ClickHouseDSN.String(), checker)
	if err != nil {
		_ = db.Close()
		return nil, err
	}
	rt := &runtime{db: db, sink: sink}
	relay, err := evidenceoutbox.NewRelay(db, newMetricsDeliverer(sink, reg), evidenceoutbox.RelayConfig{
		BatchSize:   cfg.BatchSize,
		MaxAttempts: cfg.MaxAttempts,
	})
	if err != nil {
		_ = sink.Close()
		_ = db.Close()
		return nil, err
	}
	rt.relay = relay
	return rt, nil
}

// openRelayDB opens the pool with the relay role pinned per connection via the
// PostgreSQL startup option `-c role=ibex_evidence_relay`. Pinning at connect
// time (rather than a one-off SET ROLE on a pooled connection) keeps every
// pool connection inside the relay role, including after reconnects.
func openRelayDB(ctx context.Context, dsn string, timeout time.Duration) (*sql.DB, error) {
	pinned, err := pinRelayRole(dsn)
	if err != nil {
		return nil, err
	}
	db, err := sql.Open("postgres", pinned)
	if err != nil {
		return nil, fmt.Errorf("relay: open postgres: %w", err)
	}
	db.SetMaxOpenConns(relayMaxOpenConns)
	db.SetMaxIdleConns(relayMaxIdleConns)
	pingCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	if err := db.PingContext(pingCtx); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("relay: postgres ping: %w", err)
	}
	if err := assertRelayRole(pingCtx, db); err != nil {
		_ = db.Close()
		return nil, err
	}
	return db, nil
}

// pinRelayRole returns dsn with the relay role appended as a startup option.
// Error messages intentionally never echo the DSN (it may contain credentials).
func pinRelayRole(dsn string) (string, error) {
	dsn = strings.TrimSpace(dsn)
	if dsn == "" {
		return "", fmt.Errorf("relay: IBEX_RELAY_POSTGRES_DSN is empty")
	}
	option := "-c role=" + relayRoleName
	if strings.Contains(dsn, "://") {
		return pinRelayRoleURL(dsn, option)
	}
	if strings.Contains(dsn, "options=") {
		return "", fmt.Errorf("relay: keyword-form postgres DSN with an existing options parameter is not supported; use a postgres:// URL or remove options")
	}
	return dsn + " options='-c role=" + relayRoleName + "'", nil
}

func pinRelayRoleURL(dsn, option string) (string, error) {
	u, err := url.Parse(dsn)
	if err != nil {
		return "", fmt.Errorf("relay: invalid postgres DSN; use URL form postgres://user:pass@host:port/db")
	}
	q := u.Query()
	if existing := strings.TrimSpace(q.Get("options")); existing != "" {
		q.Set("options", existing+" "+option)
	} else {
		q.Set("options", option)
	}
	u.RawQuery = q.Encode()
	return u.String(), nil
}

// assertRelayRole refuses to run unless the connection assumed the relay role.
// A login role that is not a member of ibex_evidence_relay fails here because
// PostgreSQL rejects the startup role change before the ping completes.
func assertRelayRole(ctx context.Context, db *sql.DB) error {
	var current string
	if err := db.QueryRowContext(ctx, `SELECT current_user`).Scan(&current); err != nil {
		return fmt.Errorf("relay: verify role: %w", err)
	}
	if current != relayRoleName {
		return fmt.Errorf("relay: connection assumed role %q, want %q; grant %s to the login role",
			current, relayRoleName, relayRoleName)
	}
	return nil
}

// metricsDeliverer records delivery duration/outcome around the pilot sink.
type metricsDeliverer struct {
	next    evidenceoutbox.TombstoneFencedDeliverer
	metrics *ibexmetrics.RelayRegistry
}

func newMetricsDeliverer(next evidenceoutbox.TombstoneFencedDeliverer, reg *ibexmetrics.RelayRegistry) *metricsDeliverer {
	return &metricsDeliverer{next: next, metrics: reg}
}

// DeliverWithTombstoneFence implements evidenceoutbox.TombstoneFencedDeliverer.
func (d *metricsDeliverer) DeliverWithTombstoneFence(ctx context.Context, row evidenceoutbox.OutboxRow, f evidenceoutbox.TombstoneFence) error {
	start := time.Now()
	err := d.next.DeliverWithTombstoneFence(ctx, row, f)
	result := ibexmetrics.RelayDeliveryOK
	if err != nil {
		result = ibexmetrics.RelayDeliveryError
	}
	d.metrics.ObserveDelivery(result, time.Since(start).Seconds())
	return err
}

// Deliver satisfies the legacy evidenceoutbox.Deliverer interface. Relay only
// invokes the tombstone-fenced path; this exists solely for interface fit and
// still fails closed without a fence.
func (d *metricsDeliverer) Deliver(ctx context.Context, row evidenceoutbox.OutboxRow) error {
	if row.TombstoneFence == nil {
		return fmt.Errorf("relay: delivery requires a tombstone fence")
	}
	return d.DeliverWithTombstoneFence(ctx, row, *row.TombstoneFence)
}

func closeRuntime(rt *runtime) error {
	var firstErr error
	if rt == nil {
		return nil
	}
	if rt.sink != nil {
		if err := rt.sink.Close(); err != nil {
			firstErr = fmt.Errorf("close clickhouse sink: %w", err)
		}
	}
	if rt.db != nil {
		if err := rt.db.Close(); err != nil && firstErr == nil {
			firstErr = fmt.Errorf("close postgres: %w", err)
		}
	}
	return firstErr
}
