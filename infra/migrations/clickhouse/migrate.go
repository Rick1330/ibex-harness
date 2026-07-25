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
	if dsn := firstNonEmptyEnv("CLICKHOUSE_MIGRATE_DSN", "CLICKHOUSE_DSN"); dsn != "" {
		return normalizeMigrateDSN(dsn)
	}
	return defaultMigrateDSN
}

func firstNonEmptyEnv(keys ...string) string {
	for _, k := range keys {
		if v := strings.TrimSpace(os.Getenv(k)); v != "" {
			return v
		}
	}
	return ""
}

func normalizeMigrateDSN(dsn string) string {
	dsn = strings.TrimSpace(dsn)
	u, err := url.Parse(dsn)
	if err != nil || u.Scheme == "" {
		return ensureMigrateQuery(dsn)
	}
	normalizeSchemeAndPort(u)
	liftPathDatabase(u)
	return ensureMigrateQuery(u.String())
}

func normalizeSchemeAndPort(u *url.URL) {
	if u.Scheme != "clickhouse" && u.Scheme != "tcp" {
		u.Scheme = "clickhouse"
	}
	// Only remap local compose HTTP→native; leave remote :8123 alone.
	if u.Port() == "8123" && isLocalComposeHost(u.Hostname()) {
		u.Host = u.Hostname() + ":9002"
	}
}

func isLocalComposeHost(host string) bool {
	switch strings.ToLower(host) {
	case "localhost", "127.0.0.1", "::1":
		return true
	default:
		return false
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

func ensureMigrateQuery(dsn string) string {
	u, err := url.Parse(dsn)
	if err != nil {
		return dsn
	}
	q := u.Query()
	setDefaultQuery(q, "x-multi-statement", "true")
	setDefaultQuery(q, "x-migrations-table-engine", "MergeTree")
	setDefaultQuery(q, "database", "ibex")
	u.RawQuery = q.Encode()
	return u.String()
}

func setDefaultQuery(q url.Values, key, def string) {
	if q.Get(key) == "" {
		q.Set(key, def)
	}
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

func withMigrate(dsn string, fn func(*migrate.Migrate) error) (err error) {
	m, err := newMigrate(dsn)
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
func Up(dsn string) error {
	return withMigrate(dsn, func(m *migrate.Migrate) error {
		return ignoreNoChange(m.Up())
	})
}

// Down rolls back exactly one migration step.
func Down(dsn string) error {
	return withMigrate(dsn, func(m *migrate.Migrate) error {
		return ignoreNoChange(m.Steps(-1))
	})
}

// Force sets the migration version and clears the dirty flag without running SQL.
func Force(dsn string, version int) error {
	return withMigrate(dsn, func(m *migrate.Migrate) error {
		if err := m.Force(version); err != nil {
			return fmt.Errorf("force version=%d dsn=%s: %w", version, RedactedDSN(dsn), err)
		}
		return nil
	})
}

// Version returns the current migration version and dirty flag.
func Version(dsn string) (uint, bool, error) {
	var (
		v     uint
		dirty bool
	)
	err := withMigrate(dsn, func(m *migrate.Migrate) error {
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

// RedactedDSN returns a DSN safe for logging (password removed).
func RedactedDSN(dsn string) string {
	u, err := url.Parse(dsn)
	if err != nil {
		return "(invalid dsn)"
	}
	if u.User != nil {
		// Strip password entirely (avoid placeholder strings that trip secret scanners).
		u.User = url.User(u.User.Username())
	}
	return u.String()
}
