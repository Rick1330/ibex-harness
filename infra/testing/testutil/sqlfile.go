//go:build integration

package testutil

import (
	"context"
	"os"
	"strings"
	"testing"
)

// ExecSQLFile runs a SQL script (semicolon-separated statements; `--` line comments stripped)
// on one connection so BEGIN/set_config/INSERT sequences behave like psql -f.
func ExecSQLFile(t testing.TB, dsn, filePath string) {
	t.Helper()
	raw, err := os.ReadFile(filePath)
	if err != nil {
		t.Fatalf("read sql file %s: %v", filePath, err)
	}
	db := OpenDB(t, dsn)
	defer db.Close()
	ctx := context.Background()
	conn, err := db.Conn(ctx)
	if err != nil {
		t.Fatalf("conn for %s: %v", filePath, err)
	}
	defer conn.Close()
	for i, stmt := range splitSQLStatements(string(raw)) {
		if _, err := conn.ExecContext(ctx, stmt); err != nil {
			t.Fatalf("exec statement %d in %s: %v\n%s", i+1, filePath, err, stmt)
		}
	}
}

// splitSQLStatements is a minimal splitter for fixture SQL (e.g. seed_dev.sql).
// It skips blank lines and `--` comments only; no `/* */` handling or semicolons inside quotes.
func splitSQLStatements(sql string) []string {
	return splitBySemicolon(stripSQLLineComments(sql))
}

func stripSQLLineComments(sql string) string {
	var b strings.Builder
	for _, line := range strings.Split(sql, "\n") {
		trim := strings.TrimSpace(line)
		if trim == "" || strings.HasPrefix(trim, "--") {
			continue
		}
		b.WriteString(line)
		b.WriteByte('\n')
	}
	return b.String()
}

func splitBySemicolon(body string) []string {
	var out []string
	for _, part := range strings.Split(body, ";") {
		if stmt := strings.TrimSpace(part); stmt != "" {
			out = append(out, stmt)
		}
	}
	return out
}
