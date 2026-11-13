package clickhouse

import (
	"regexp"
	"strings"
	"testing"
)

// P2-03: ClickHouse schema evolution has no gate.
//
// golang-migrate applies the embedded *.up.sql files verbatim, and ClickHouse
// has no transactional rollback for most DDL. A `DROP TABLE`, a `TRUNCATE`, or a
// `DELETE FROM` in an up migration destroys production analytics data with no
// recovery path. This gate refuses the destructive forms listed below before the
// migration set can be applied.
//
// Detected, case-insensitively, in executable SQL only (comments, string
// literals, and quoted identifiers are blanked before matching):
//
//	DROP TABLE   DROP COLUMN   CLEAR COLUMN
//	DELETE FROM  RENAME        TRUNCATE
//	ALTER … DROP    ALTER … DELETE
//
// The last two are scoped to statements that start with ALTER, because
// `ALTER TABLE … DROP PARTITION` (or DROP INDEX / DROP PROJECTION) and
// `ALTER TABLE … DELETE WHERE` destroy data without naming a table or a column.
//
// Not detected, and therefore still a manual review item: DROP DATABASE,
// DROP VIEW, DROP DICTIONARY, DROP FUNCTION, DROP USER/ROLE, OPTIMIZE … FINAL,
// and every statement that rewrites rather than removes data (MODIFY COLUMN,
// MODIFY TTL, ATTACH/DETACH PARTITION). Extending the gate is one entry in
// destructiveDDLDetectors or alterScopedDetectors plus one fixture case, and is
// deliberately left to a decision that names the failure it prevents.
//
// The gate is a unit test, not a runtime check: it scans the embedded migration
// files, so it runs offline with no ClickHouse container.

// ddlDetector is one refused pattern: the name a failure reports and the
// matcher that recognises it in an uppercased statement.
type ddlDetector struct {
	pattern string
	re      *regexp.Regexp
}

// destructiveDDLDetectors match anywhere in a statement. Matching runs against
// an uppercased statement with comments and quoted text removed, so prose and
// column defaults cannot trip the gate.
var destructiveDDLDetectors = []ddlDetector{
	{"DROP TABLE", regexp.MustCompile(`\bDROP\s+TABLE\b`)},
	{"DROP COLUMN", regexp.MustCompile(`\bDROP\s+COLUMN\b`)},
	{"CLEAR COLUMN", regexp.MustCompile(`\bCLEAR\s+COLUMN\b`)},
	{"DELETE FROM", regexp.MustCompile(`\bDELETE\s+FROM\b`)},
	{"RENAME", regexp.MustCompile(`\bRENAME\b`)},
	{"TRUNCATE", regexp.MustCompile(`\bTRUNCATE\b`)},
}

// alterScopedDetectors match only when the statement starts with ALTER. They are
// separate from the table above because `ALTER TABLE … DROP PARTITION` (or
// DROP INDEX / DROP PROJECTION) and `ALTER TABLE … DELETE WHERE` destroy data
// without naming a table or a column.
var alterScopedDetectors = []ddlDetector{
	{alterDropPattern, regexp.MustCompile(`\bDROP\b`)},
	{alterDeletePattern, regexp.MustCompile(`\bDELETE\b`)},
}

// Finding names for the two ALTER-scoped rules.
const (
	alterDropPattern   = "ALTER ... DROP"
	alterDeletePattern = "ALTER ... DELETE"
)

// reviewedExceptions is the companion record P2-03 allows: a migration file
// name mapped to the written reason it may contain destructive DDL. It is
// empty today — no ClickHouse migration needs an exception — and every entry is
// checked against the embedded file set by
// TestUnit_ReviewedExceptions_NameRealMigrations, so a stale entry fails.
var reviewedExceptions = map[string]string{}

// destructiveFinding is one refused statement.
type destructiveFinding struct {
	pattern string
	snippet string
}

// TestUnit_UpMigrations_NoDestructiveDDL is the gate itself.
func TestUnit_UpMigrations_NoDestructiveDDL(t *testing.T) {
	t.Parallel()

	names := upMigrationNames(t)
	if len(names) == 0 {
		t.Fatal("no up migrations scanned; the gate would pass vacuously")
	}
	for _, name := range names {
		assertNoDestructiveDDL(t, name)
	}
}

// upMigrationNames lists the embedded up migrations in directory order.
func upMigrationNames(t *testing.T) []string {
	t.Helper()
	entries, err := migrationFiles.ReadDir(".")
	if err != nil {
		t.Fatalf("read migrations: %v", err)
	}
	var names []string
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".up.sql") {
			continue
		}
		names = append(names, e.Name())
	}
	return names
}

// assertNoDestructiveDDL reports every refused statement in one migration,
// skipping the files a written exception names.
func assertNoDestructiveDDL(t *testing.T, name string) {
	t.Helper()
	if _, ok := reviewedExceptions[name]; ok {
		return
	}
	body, err := migrationFiles.ReadFile(name)
	if err != nil {
		t.Fatalf("read %s: %v", name, err)
	}
	for _, f := range destructiveDDLFindings(string(body)) {
		t.Errorf("%s: destructive DDL (%s): %s", name, f.pattern, f.snippet)
	}
}

// TestUnit_ReviewedExceptions_NameRealMigrations keeps the exception list
// honest: an entry for a file that does not exist would silently widen nothing
// today and hide a rename tomorrow.
func TestUnit_ReviewedExceptions_NameRealMigrations(t *testing.T) {
	t.Parallel()

	for name, reason := range reviewedExceptions {
		if strings.TrimSpace(reason) == "" {
			t.Errorf("exception %s has no written reason", name)
		}
		if _, err := migrationFiles.ReadFile(name); err != nil {
			t.Errorf("exception %s does not name an embedded migration: %v", name, err)
		}
	}
}

// TestUnit_DestructiveDDL_CatchesPatterns proves each refused form is caught
// and reported under its own name.
func TestUnit_DestructiveDDL_CatchesPatterns(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		sql  string
		want string
	}{
		{"drop table", "DROP TABLE ibex.llm_traces", "DROP TABLE"},
		{"drop table if exists", "DROP TABLE IF EXISTS ibex.llm_traces", "DROP TABLE"},
		{"drop column", "ALTER TABLE ibex.llm_traces DROP COLUMN provider", "DROP COLUMN"},
		{"drop column if exists", "ALTER TABLE ibex.x DROP COLUMN IF EXISTS y", "DROP COLUMN"},
		{"rename table", "RENAME TABLE ibex.llm_traces TO ibex.llm_traces_old", "RENAME"},
		{"rename column", "ALTER TABLE ibex.x RENAME COLUMN a TO b", "RENAME"},
		{"alter drop partition", "ALTER TABLE ibex.llm_traces DROP PARTITION 202601", "ALTER ... DROP"},
		{"alter drop index", "ALTER TABLE ibex.x DROP INDEX idx_y", "ALTER ... DROP"},
		{"alter drop projection", "ALTER TABLE ibex.x DROP PROJECTION p", "ALTER ... DROP"},
		{"alter delete where", "ALTER TABLE ibex.llm_traces DELETE WHERE event_date < '2026-01-01'", "ALTER ... DELETE"},
		{"alter delete on cluster", "ALTER TABLE ibex.llm_traces ON CLUSTER ibex DELETE WHERE org_id = 'x'", "ALTER ... DELETE"},
		{"clear column", "ALTER TABLE ibex.llm_traces CLEAR COLUMN provider IN PARTITION 202601", "CLEAR COLUMN"},
		{"clear column if exists", "ALTER TABLE ibex.x CLEAR COLUMN IF EXISTS y", "CLEAR COLUMN"},
		{"delete from", "DELETE FROM ibex.llm_traces WHERE org_id = '00000000-0000-0000-0000-000000000000'", "DELETE FROM"},
		{"delete from on cluster", "DELETE FROM ibex.llm_traces ON CLUSTER ibex WHERE event_date < today()", "DELETE FROM"},
		{"truncate table", "TRUNCATE TABLE ibex.llm_traces", "TRUNCATE"},
		{"truncate bare", "TRUNCATE ibex.llm_traces", "TRUNCATE"},
		{"lowercase", "drop table ibex.llm_traces", "DROP TABLE"},
		{
			// Backslash escaping: the scanner must stay inside the literal at
			// `\'`, or the statement after it is blanked and the drop is missed.
			"backslash escaped quote hides a drop",
			`SELECT 'it\'s fine'); DROP TABLE ibex.llm_traces`,
			"DROP TABLE",
		},
		{
			// The backtick scanner must close before the drop, not run past it.
			"backtick identifier closes before a drop",
			"CREATE TABLE ibex.y (`a\\`b` String) ENGINE = MergeTree ORDER BY tuple();\nDROP TABLE ibex.z",
			"DROP TABLE",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			findings := destructiveDDLFindings(tc.sql)
			if !hasPattern(findings, tc.want) {
				t.Fatalf("%q: want pattern %q, got %v", tc.sql, tc.want, findings)
			}
		})
	}
}

// TestUnit_DestructiveDDL_AllowsAdditiveDDL proves the gate does not block the
// additive evolution the ClickHouse migration set actually uses.
func TestUnit_DestructiveDDL_AllowsAdditiveDDL(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		sql  string
	}{
		{"create database", "CREATE DATABASE IF NOT EXISTS ibex"},
		{
			"create table",
			`CREATE TABLE IF NOT EXISTS ibex.llm_traces
(
    org_id UUID,
    requested_at DateTime64(3, 'UTC'),
    event_date Date MATERIALIZED toDate(requested_at)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (org_id, requested_at)
TTL event_date + INTERVAL 90 DAY
SETTINGS index_granularity = 8192`,
		},
		{
			"create materialized view",
			`CREATE MATERIALIZED VIEW IF NOT EXISTS ibex.usage_hourly
ENGINE = SummingMergeTree()
ORDER BY (org_id, hour)
AS SELECT org_id, toStartOfHour(occurred_at) AS hour, sum(total_tokens) AS tokens
FROM ibex.usage_facts
GROUP BY org_id, hour`,
		},
		{
			"alter add column",
			`ALTER TABLE ibex.llm_traces
    ADD COLUMN IF NOT EXISTS original_model Nullable(String),
    ADD COLUMN IF NOT EXISTS fallback_model Nullable(String)`,
		},
		{"alter modify ttl", "ALTER TABLE ibex.llm_traces MODIFY TTL event_date + INTERVAL 30 DAY"},
		{"add index", "ALTER TABLE ibex.x ADD INDEX idx_y org_id TYPE minmax GRANULARITY 1"},
		{"create view", "CREATE VIEW IF NOT EXISTS ibex.v AS SELECT org_id FROM ibex.x"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if findings := destructiveDDLFindings(tc.sql); len(findings) != 0 {
				t.Fatalf("%q: want no findings, got %v", tc.name, findings)
			}
		})
	}
}

// TestUnit_DestructiveDDL_IgnoresCommentsAndLiterals proves that prose and
// column defaults cannot trip the gate. Migration 000004 carries the sentence
// "drops are logged/metric'd only"; a naive substring scan fails on it.
//
// The escaped-quote and backtick cases pin the false-positive half of the
// escaping bug: a keyword inside `'it\'s a DROP TABLE …'` or inside a
// backtick-quoted identifier is data, not a statement.
func TestUnit_DestructiveDDL_IgnoresCommentsAndLiterals(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		sql  string
	}{
		{
			"line comment",
			"-- Write-path failure policy: FAIL-OPEN, drops are logged/metric'd only.\n-- Never DROP TABLE or TRUNCATE here.\nCREATE TABLE ibex.y (org_id UUID) ENGINE = MergeTree ORDER BY org_id",
		},
		{
			"block comment",
			"/* DROP TABLE ibex.x; TRUNCATE TABLE ibex.x; */\nCREATE TABLE ibex.y (org_id UUID) ENGINE = MergeTree ORDER BY org_id",
		},
		{
			"string literal default",
			"CREATE TABLE ibex.y (note String DEFAULT 'drop column') ENGINE = MergeTree ORDER BY note",
		},
		{
			"backslash escaped quote around a keyword",
			`CREATE TABLE ibex.y (note String DEFAULT 'it\'s a DROP TABLE, not a command') ENGINE = MergeTree ORDER BY note`,
		},
		{
			"backtick identifier escapes a keyword",
			"CREATE TABLE ibex.y (`odd\\`DROP TABLE` String) ENGINE = MergeTree ORDER BY tuple()",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if findings := destructiveDDLFindings(tc.sql); len(findings) != 0 {
				t.Fatalf("%q: want no findings, got %v", tc.name, findings)
			}
		})
	}
}

// TestUnit_DestructiveDDL_ScopesAlterDropToItsStatement proves the ALTER … DROP
// rule does not leak across statement boundaries: an additive ALTER followed by
// an unrelated statement is not reported as destructive.
func TestUnit_DestructiveDDL_ScopesAlterDropToItsStatement(t *testing.T) {
	t.Parallel()

	sql := "ALTER TABLE ibex.x ADD COLUMN y String;\nCREATE TABLE ibex.z (org_id UUID) ENGINE = MergeTree ORDER BY org_id"
	if findings := destructiveDDLFindings(sql); len(findings) != 0 {
		t.Fatalf("want no findings, got %v", findings)
	}
}

func hasPattern(findings []destructiveFinding, want string) bool {
	for _, f := range findings {
		if f.pattern == want {
			return true
		}
	}
	return false
}

// destructiveDDLFindings returns every refused statement in sqlText. Comments
// and string literals are blanked before matching, so only executable SQL is
// considered.
func destructiveDDLFindings(sqlText string) []destructiveFinding {
	var findings []destructiveFinding
	for _, stmt := range splitSQLStatements(stripSQLCommentsAndLiterals(sqlText)) {
		findings = append(findings, stmt.findings()...)
	}
	return findings
}

// sqlStatement is one executable statement, kept in its original casing for the
// failure snippet and in its uppercased form for matching.
type sqlStatement struct {
	text  string
	upper string
}

// findings returns the refused patterns in the statement: one per detector that
// matches, plus the ALTER-scoped rules when the statement is an ALTER that drops
// or deletes data without naming a table or a column.
func (s sqlStatement) findings() []destructiveFinding {
	if s.upper == "" {
		return nil
	}
	findings := matchDetectors(destructiveDDLDetectors, s)
	if strings.HasPrefix(s.upper, "ALTER") {
		findings = append(findings, matchDetectors(alterScopedDetectors, s)...)
	}
	return findings
}

// matchDetectors returns one finding per detector that matches the statement.
func matchDetectors(detectors []ddlDetector, s sqlStatement) []destructiveFinding {
	var findings []destructiveFinding
	for _, d := range detectors {
		if d.re.MatchString(s.upper) {
			findings = append(findings, destructiveFinding{pattern: d.pattern, snippet: s.snippet()})
		}
	}
	return findings
}

const maxSnippetLen = 120

// snippet is the statement on one line, truncated for a failure message.
func (s sqlStatement) snippet() string {
	snippet := strings.Join(strings.Fields(s.text), " ")
	if len(snippet) > maxSnippetLen {
		return snippet[:maxSnippetLen] + "…"
	}
	return snippet
}

// splitSQLStatements splits on `;` and drops the blank segments. It runs after
// comment and literal stripping, so a semicolon inside a comment or a string
// cannot split a statement.
func splitSQLStatements(stripped string) []sqlStatement {
	segments := strings.Split(stripped, ";")
	statements := make([]sqlStatement, 0, len(segments))
	for _, segment := range segments {
		upper := strings.ToUpper(strings.TrimSpace(segment))
		if upper == "" {
			continue
		}
		statements = append(statements, sqlStatement{text: segment, upper: upper})
	}
	return statements
}

// stripSQLCommentsAndLiterals replaces `--` line comments, `/* */` block
// comments, single-quoted string literals, and backtick-quoted identifiers with
// spaces, preserving newlines and byte offsets so the statement text stays
// readable in a failure message.
func stripSQLCommentsAndLiterals(sqlText string) string {
	scanner := sqlScanner{src: sqlText}
	scanner.out.Grow(len(sqlText))
	for scanner.pos < len(scanner.src) {
		scanner.step()
	}
	return scanner.out.String()
}

// sqlScanner is the stripper's state: the input, the byte it is reading, and the
// output it is writing. Every token writes exactly as many bytes as it consumes,
// so the result keeps the input's offsets.
type sqlScanner struct {
	src string
	out strings.Builder
	pos int
}

// step consumes one token: a comment, a quoted literal or identifier, or one
// byte of SQL.
func (s *sqlScanner) step() {
	switch {
	case s.atLineComment():
		s.skipLineComment()
	case s.atBlockComment():
		s.skipBlockComment()
	case s.atQuote():
		s.skipQuoted()
	default:
		s.out.WriteByte(s.peek())
		s.pos++
	}
}

// atQuote reports whether the scanner is on a byte that opens quoted text:
// a single-quoted string literal or a backtick-quoted identifier.
func (s *sqlScanner) atQuote() bool {
	quote := s.peek()
	return quote == '\'' || quote == '`'
}

// peek returns the byte at pos, or 0 at end of input.
func (s *sqlScanner) peek() byte {
	if s.pos < len(s.src) {
		return s.src[s.pos]
	}
	return 0
}

// next returns the byte after pos, or 0 at end of input.
func (s *sqlScanner) next() byte {
	if s.pos+1 < len(s.src) {
		return s.src[s.pos+1]
	}
	return 0
}

func (s *sqlScanner) atLineComment() bool { return s.peek() == '-' && s.next() == '-' }

func (s *sqlScanner) atBlockComment() bool { return s.peek() == '/' && s.next() == '*' }

func (s *sqlScanner) atBlockEnd() bool { return s.peek() == '*' && s.next() == '/' }

// atDoubledQuote reports whether the scanner is on the two-byte escape that
// writes one quote inside quoted text: two single quotes, or two backticks.
func (s *sqlScanner) atDoubledQuote(quote byte) bool {
	return s.peek() == quote && s.next() == quote
}

// skipLineComment blanks `-- ...` through the end of the line, keeping the
// newline that ends it.
func (s *sqlScanner) skipLineComment() {
	s.out.WriteString("  ")
	s.pos += 2
	for s.pos < len(s.src) {
		if s.peek() == '\n' {
			s.out.WriteByte('\n')
			s.pos++
			return
		}
		s.out.WriteByte(' ')
		s.pos++
	}
}

// skipBlockComment blanks `/* ... */`, keeping the newlines inside it.
func (s *sqlScanner) skipBlockComment() {
	s.out.WriteString("  ")
	s.pos += 2
	for s.pos < len(s.src) {
		if s.atBlockEnd() {
			s.out.WriteString("  ")
			s.pos += 2
			return
		}
		s.writeBlank()
		s.pos++
	}
}

// skipQuoted blanks the inside of a quoted literal or identifier, keeping its
// quotes and its escapes.
//
// ClickHouse accepts two escapes, and both must be consumed as one unit or the
// closing quote is found in the wrong place. A doubled quote (two single quotes
// or two backticks) writes one quote; a backslash escapes the byte after it
// (`\'`, a backslash before a backtick, `\\`). Ignoring the backslash form
// produces both halves of the bug: it hides a statement that follows the
// literal (`'it\'s fine'); DROP TABLE ibex.llm_traces`) and it invents one
// inside it (`'it\'s a DROP TABLE, not a command'`).
func (s *sqlScanner) skipQuoted() {
	quote := s.peek()
	s.out.WriteByte(quote)
	s.pos++
	for s.pos < len(s.src) {
		switch {
		case s.atDoubledQuote(quote):
			s.out.WriteByte(quote)
			s.out.WriteByte(quote)
			s.pos += 2
		case s.peek() == quote:
			s.out.WriteByte(quote)
			s.pos++
			return
		case s.peek() == '\\':
			s.skipBackslashEscape()
		default:
			s.writeBlank()
			s.pos++
		}
	}
}

// skipBackslashEscape blanks a backslash and the byte it escapes, keeping a
// newline if the escaped byte is one. A backslash at the end of the input
// escapes nothing and is blanked alone.
func (s *sqlScanner) skipBackslashEscape() {
	s.writeBlank()
	s.pos++
	if s.pos < len(s.src) {
		s.writeBlank()
		s.pos++
	}
}

// writeBlank blanks the current byte, keeping a newline so line structure
// survives.
func (s *sqlScanner) writeBlank() {
	if s.peek() == '\n' {
		s.out.WriteByte('\n')
		return
	}
	s.out.WriteByte(' ')
}
