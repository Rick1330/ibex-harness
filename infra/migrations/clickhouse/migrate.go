package clickhouse

import (
	"embed"
	"errors"
	"fmt"
	"net/url"
	"os"
	"strings"

	// Registers the ClickHouse database/sql driver used by golang-migrate.
	_ "github.com/ClickHouse/clickhouse-go"
	"github.com/golang-migrate/migrate/v4"
	// Registers the ClickHouse database driver with golang-migrate.
	_ "github.com/golang-migrate/migrate/v4/database/clickhouse"
	"github.com/golang-migrate/migrate/v4/source/iofs"
)

//go:embed *.sql
var migrationFiles embed.FS

// Native protocol on compose host port 9002 (container 9000). HTTP 8123 is for apps (2.5.2).
const defaultMigrateDSN = "clickhouse://default:@localhost:9002?database=ibex&x-multi-statement=true&x-migrations-table-engine=MergeTree"

// Conn is a golang-migrate ClickHouse connection (native TCP).
type Conn struct {
	raw string
}

// ParseConn normalizes a ClickHouse migrate URL.
func ParseConn(raw string) Conn {
	return Conn{raw: normalizeMigrateURL(raw)}
}

// ResolveConn returns the migrate connection from env or the local compose default.
func ResolveConn() Conn {
	if v := strings.TrimSpace(os.Getenv("CLICKHOUSE_MIGRATE_DSN")); v != "" {
		return ParseConn(v)
	}
	if v := strings.TrimSpace(os.Getenv("CLICKHOUSE_DSN")); v != "" {
		return ParseConn(v)
	}
	return Conn{raw: defaultMigrateDSN}
}

// ResolveDSN returns the ClickHouse URL for golang-migrate (native TCP).
func ResolveDSN() string {
	return ResolveConn().raw
}

// String returns the raw DSN.
func (c Conn) String() string {
	return c.raw
}

// Redacted returns a DSN safe for logging (password removed).
func (c Conn) Redacted() string {
	u, err := url.Parse(c.raw)
	if err != nil {
		return "(invalid dsn)"
	}
	if u.User != nil {
		u.User = url.User(u.User.Username())
	}
	return u.String()
}

func normalizeMigrateURL(raw string) string {
	raw = strings.TrimSpace(raw)
	u, err := url.Parse(raw)
	if err != nil || u.Scheme == "" {
		return applyMigrateQueryDefaults(raw)
	}
	normalizeSchemeAndPort(u)
	liftPathDatabase(u)
	ensureMigrateQuery(u)
	return u.String()
}

func applyMigrateQueryDefaults(raw string) string {
	u, err := url.Parse(raw)
	if err != nil {
		return raw
	}
	ensureMigrateQuery(u)
	return u.String()
}

func normalizeSchemeAndPort(u *url.URL) {
	if u.Scheme != "clickhouse" && u.Scheme != "tcp" {
		u.Scheme = "clickhouse"
	}
	host := strings.ToLower(u.Hostname())
	local := host == "localhost" || host == "127.0.0.1" || host == "::1"
	if u.Port() == "8123" && local {
		u.Host = u.Hostname() + ":9002"
	}
}

func liftPathDatabase(u *url.URL) {
	db := strings.Trim(u.Path, "/")
	if db == "" {
		return
	}
	q := u.Query()
	if q.Get("database") == "" {
		q.Set("database", db)
	}
	u.Path = ""
	u.RawQuery = q.Encode()
}

func ensureMigrateQuery(u *url.URL) {
	q := u.Query()
	if q.Get("x-multi-statement") == "" {
		q.Set("x-multi-statement", "true")
	}
	if q.Get("x-migrations-table-engine") == "" {
		q.Set("x-migrations-table-engine", "MergeTree")
	}
	if q.Get("database") == "" {
		q.Set("database", "ibex")
	}
	u.RawQuery = q.Encode()
}

func newMigrate(c Conn) (*migrate.Migrate, error) {
	source, err := iofs.New(migrationFiles, ".")
	if err != nil {
		return nil, fmt.Errorf("migration source: %w", err)
	}
	m, err := migrate.NewWithSourceInstance("iofs", source, c.raw)
	if err != nil {
		return nil, fmt.Errorf("migrate instance: %w", err)
	}
	return m, nil
}

func withMigrate(c Conn, fn func(*migrate.Migrate) error) (err error) {
	m, err := newMigrate(c)
	if err != nil {
		return err
	}
	defer func() {
		if cerr := closeMigrate(m); cerr != nil && err == nil {
			err = cerr
		}
	}()
	return fn(m)
}

func ignoreNoChange(err error) error {
	if err != nil && !errors.Is(err, migrate.ErrNoChange) {
		return err
	}
	return nil
}

// Up applies all pending migrations.
func Up(c Conn) error {
	return withMigrate(c, func(m *migrate.Migrate) error {
		return ignoreNoChange(m.Up())
	})
}

// Down rolls back exactly one migration step.
func Down(c Conn) error {
	return withMigrate(c, func(m *migrate.Migrate) error {
		return ignoreNoChange(m.Steps(-1))
	})
}

// Force sets the migration version and clears the dirty flag without running SQL.
func Force(c Conn, version int) error {
	return withMigrate(c, func(m *migrate.Migrate) error {
		if err := m.Force(version); err != nil {
			return fmt.Errorf("force version=%d dsn=%s: %w", version, c.Redacted(), err)
		}
		return nil
	})
}

// Version returns the current migration version and dirty flag.
func Version(c Conn) (uint, bool, error) {
	var (
		v     uint
		dirty bool
	)
	err := withMigrate(c, func(m *migrate.Migrate) error {
		raw, d, verr := m.Version()
		if verr != nil && !errors.Is(verr, migrate.ErrNilVersion) {
			return verr
		}
		if errors.Is(verr, migrate.ErrNilVersion) {
			return nil
		}
		v, dirty = raw, d
		return nil
	})
	return v, dirty, err
}

func closeMigrate(m *migrate.Migrate) error {
	srcErr, dbErr := m.Close()
	if srcErr != nil {
		return srcErr
	}
	return dbErr
}
