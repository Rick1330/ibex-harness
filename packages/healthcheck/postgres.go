package healthcheck

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
)

// PostgresSelect1 returns a checker that runs SELECT 1 against db.
func PostgresSelect1(db *sql.DB) Checker {
	return func(ctx context.Context) error {
		if db == nil {
			return errors.New("postgres database not configured")
		}
		var n int
		if err := db.QueryRowContext(ctx, "SELECT 1").Scan(&n); err != nil {
			return fmt.Errorf("postgres unreachable: %w", err)
		}
		if n != 1 {
			return errors.New("postgres unexpected SELECT 1 result")
		}
		return nil
	}
}
