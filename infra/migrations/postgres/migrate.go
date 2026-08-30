package postgres

import (
	"embed"
	"errors"
	"fmt"
	"net/url"
	"os"
	"strings"

	"github.com/golang-migrate/migrate/v4"
	_ "github.com/golang-migrate/migrate/v4/database/postgres"
	"github.com/golang-migrate/migrate/v4/source/iofs"
)

//go:embed *.sql
var migrationFiles embed.FS

const defaultMigrateDSN = "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"

// ResolveDSN returns the database URL for golang-migrate (lib/pq / postgres driver).
func ResolveDSN() string {
	if dsn := strings.TrimSpace(os.Getenv("POSTGRES_MIGRATE_DSN")); dsn != "" {
		return normalizePostgresDSN(dsn)
	}
	if dsn := strings.TrimSpace(os.Getenv("POSTGRES_DSN")); dsn != "" {
		return normalizePostgresDSN(dsn)
	}
	return defaultMigrateDSN
}

func normalizePostgresDSN(dsn string) string {
	dsn = strings.TrimSpace(dsn)
	if idx := strings.Index(dsn, "://"); idx >= 0 {
		scheme := dsn[:idx]
		rest := dsn[idx+3:]
		if plus := strings.Index(scheme, "+"); plus >= 0 {
			scheme = scheme[:plus]
		}
		if scheme == "postgresql" || scheme == "postgres" {
			dsn = "postgres://" + rest
		}
	}
	if !strings.Contains(dsn, "sslmode=") {
		sep := "?"
		if strings.Contains(dsn, "?") {
			sep = "&"
		}
		dsn += sep + "sslmode=disable"
	}
	return dsn
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
