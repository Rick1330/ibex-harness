package clickhouse

import (
	"embed"
	"errors"
	"fmt"
	"net/url"
	"os"
	"strings"

	_ "github.com/ClickHouse/clickhouse-go"
	"github.com/golang-migrate/migrate/v4"
	_ "github.com/golang-migrate/migrate/v4/database/clickhouse"
	"github.com/golang-migrate/migrate/v4/source/iofs"
)

//go:embed *.sql
var migrationFiles embed.FS

// Native protocol on compose host port 9002 (container 9000). HTTP 8123 is for apps (2.5.2).
const defaultMigrateDSN = "clickhouse://default:@localhost:9002?database=ibex&x-multi-statement=true&x-migrations-table-engine=MergeTree"

// ResolveDSN returns the ClickHouse URL for golang-migrate (native TCP).
func ResolveDSN() string {
	if dsn := strings.TrimSpace(os.Getenv("CLICKHOUSE_MIGRATE_DSN")); dsn != "" {
		return normalizeMigrateDSN(dsn)
	}
	if dsn := strings.TrimSpace(os.Getenv("CLICKHOUSE_DSN")); dsn != "" {
		return normalizeMigrateDSN(dsn)
	}
	return defaultMigrateDSN
}

func normalizeMigrateDSN(dsn string) string {
	dsn = strings.TrimSpace(dsn)
	u, err := url.Parse(dsn)
	if err != nil || u.Scheme == "" {
		return ensureMigrateQuery(dsn)
	}
	if u.Scheme != "clickhouse" && u.Scheme != "tcp" {
		u.Scheme = "clickhouse"
	}
	// Remap common HTTP compose port to native host mapping for migrate.
	if u.Port() == "8123" {
		u.Host = u.Hostname() + ":9002"
	}
	if db := strings.Trim(u.Path, "/"); db != "" {
		q := u.Query()
		if q.Get("database") == "" {
			q.Set("database", db)
		}
		u.Path = ""
		u.RawQuery = q.Encode()
	}
	return ensureMigrateQuery(u.String())
}

func ensureMigrateQuery(dsn string) string {
	u, err := url.Parse(dsn)
	if err != nil {
		return dsn
	}
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
	return u.String()
}

func newMigrate(dsn string) (*migrate.Migrate, error) {
	source, err := iofs.New(migrationFiles, ".")
	if err != nil {
		return nil, fmt.Errorf("migration source: %w", err)
	}
	m, err := migrate.NewWithSourceInstance("iofs", source, dsn)
	if err != nil {
		return nil, fmt.Errorf("migrate instance: %w", err)
	}
	return m, nil
}

// Up applies all pending migrations.
func Up(dsn string) error {
	m, err := newMigrate(dsn)
	if err != nil {
		return err
	}
	defer closeMigrate(m)
	if err := m.Up(); err != nil && !errors.Is(err, migrate.ErrNoChange) {
		return err
	}
	return nil
}

// Down rolls back exactly one migration step.
func Down(dsn string) error {
	m, err := newMigrate(dsn)
	if err != nil {
		return err
	}
	defer closeMigrate(m)
	if err := m.Steps(-1); err != nil && !errors.Is(err, migrate.ErrNoChange) {
		return err
	}
	return nil
}

// Force sets the migration version and clears the dirty flag without running SQL.
func Force(dsn string, version int) error {
	m, err := newMigrate(dsn)
	if err != nil {
		return fmt.Errorf("force newMigrate dsn=%s: %w", RedactedDSN(dsn), err)
	}
	defer closeMigrate(m)
	if err := m.Force(version); err != nil {
		return fmt.Errorf("force version=%d: %w", version, err)
	}
	return nil
}

// Version returns the current migration version and dirty flag.
func Version(dsn string) (uint, bool, error) {
	m, err := newMigrate(dsn)
	if err != nil {
		return 0, false, err
	}
	defer closeMigrate(m)

	v, dirty, err := m.Version()
	if err != nil && !errors.Is(err, migrate.ErrNilVersion) {
		return 0, false, err
	}
	if errors.Is(err, migrate.ErrNilVersion) {
		return 0, false, nil
	}
	return v, dirty, nil
}

func closeMigrate(m *migrate.Migrate) {
	if srcErr, dbErr := m.Close(); srcErr != nil || dbErr != nil {
		_ = srcErr
		_ = dbErr
	}
}

// RedactedDSN returns a DSN safe for logging (password removed).
func RedactedDSN(dsn string) string {
	u, err := url.Parse(dsn)
	if err != nil {
		return "(invalid dsn)"
	}
	if u.User != nil {
		user := u.User.Username()
		u.User = url.UserPassword(user, "REDACTED")
	}
	return u.String()
}
