package postgres

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"errors"
	"fmt"
	"net/url"
	"os"
	"strings"
	"time"

	_ "github.com/lib/pq" // registers the PostgreSQL driver for database/sql
	"golang.org/x/crypto/pbkdf2"
)

// SCRAM-SHA-256 parameters. PostgreSQL's `psql \password` uses the same
// construction: PBKDF2-HMAC-SHA256 with 4096 iterations and a 16-byte salt.
const (
	scramIterations = 4096
	scramSaltBytes  = 16
)

// provisionTarget describes one capability login: its environment secret, the
// privileged roles it must not reach, and the roles it must be able to assume.
type provisionTarget struct {
	role           string
	envName        string
	forbiddenRoles []string
	requiredRoles  []string
}

// provisionTargets is the complete capability-login model. ibex_worker is
// deliberately allowed to reach ibex_purge; ibex_bootstrap is allowed no
// membership at all; ibex_auth is allowed ibex_app but must never reach a
// service, purge, bootstrap, runtime or evidence-relay identity. Every target
// forbids every other privileged role, so a stray GRANT is caught at provision
// time instead of widening a login silently.
//
// ibex_runtime is on ibex_auth's forbidden list even though both hold ibex_app
// today. They are separate login identities: a membership would let the auth
// login act as the runtime login, and would inherit whatever capability
// ibex_runtime is granted in a later migration without a second review.
var provisionTargets = []provisionTarget{
	{
		role:           "ibex_runtime",
		envName:        "IBEX_RUNTIME_DB_PASSWORD",
		forbiddenRoles: []string{"ibex_service", "ibex_purge", "ibex_bootstrap", "ibex_auth"},
		requiredRoles:  []string{"ibex_app"},
	},
	{
		role:           "ibex_worker",
		envName:        "IBEX_WORKER_DB_PASSWORD",
		forbiddenRoles: []string{"ibex_service", "ibex_bootstrap", "ibex_auth"},
		requiredRoles:  []string{"ibex_app", "ibex_purge"},
	},
	{
		role:           "ibex_bootstrap",
		envName:        "IBEX_BOOTSTRAP_DB_PASSWORD",
		forbiddenRoles: []string{"ibex_service", "ibex_purge", "ibex_app", "ibex_auth"},
		requiredRoles:  nil,
	},
	{
		role:           "ibex_auth",
		envName:        "IBEX_AUTH_DB_PASSWORD",
		forbiddenRoles: []string{"ibex_service", "ibex_purge", "ibex_bootstrap", "ibex_runtime", "ibex_evidence_relay"},
		requiredRoles:  []string{"ibex_app"},
	},
}

// provisionSecrets maps a role name to its plaintext capability secret.
type provisionSecrets map[string]string

// provisionCredential pairs a target with its resolved secret so worker
// functions take one struct rather than several strings.
type provisionCredential struct {
	target   provisionTarget
	password string
}

// provisionRun carries the DSN and secrets through one provisioning attempt.
type provisionRun struct {
	dsn     string
	secrets provisionSecrets
}

// ownerCredential is the migration DSN's owner password.
type ownerCredential struct {
	password string
}

// scramInput is the input to the SCRAM verifier derivation.
type scramInput struct {
	password   string
	salt       []byte
	iterations int
}

// sqlText is a value that must be emitted as a single-quoted SQL literal.
type sqlText struct {
	value string
}

// sqlIdentifier is a value that must be emitted as a quoted SQL identifier.
type sqlIdentifier struct {
	value string
}

// redaction is a message and the secret to remove from it.
type redaction struct {
	message string
	secret  string
}

// Provision sets the four capability-login passwords in one transaction and
// refuses to commit unless every role is safe, cannot reach a privileged
// identity, and can assume the roles it requires. Each statement carries a
// pre-computed SCRAM-SHA-256 verifier, never the plaintext.
func Provision(dsn string) error {
	if err := validateDSNScheme(dsn); err != nil {
		return err
	}
	password, err := dsnPassword(dsn)
	if err != nil {
		return errors.New("provision: cannot determine the owner credential from the migration DSN")
	}
	secrets, err := resolveProvisionSecrets(os.Getenv, ownerCredential{password: password})
	if err != nil {
		return err
	}
	return runProvision(provisionRun{dsn: dsn, secrets: secrets})
}

// runProvision opens one transaction, applies every target, and commits.
func runProvision(run provisionRun) error {
	db, err := sql.Open("postgres", run.dsn)
	if err != nil {
		return sanitizeProvisionError(fmt.Errorf("provision: open database: %w", err), run)
	}
	defer db.Close()

	tx, err := db.Begin()
	if err != nil {
		return sanitizeProvisionError(fmt.Errorf("provision: begin: %w", err), run)
	}
	defer func() { _ = tx.Rollback() }()

	if err := applyProvision(tx, run.secrets); err != nil {
		return sanitizeProvisionError(err, run)
	}
	if err := tx.Commit(); err != nil {
		return sanitizeProvisionError(fmt.Errorf("provision: commit: %w", err), run)
	}
	return nil
}

// applyProvision sets the session mode and provisions every target in order.
func applyProvision(tx *sql.Tx, secrets provisionSecrets) error {
	if _, err := tx.Exec(`SET LOCAL standard_conforming_strings = on`); err != nil {
		return fmt.Errorf("provision: set standard_conforming_strings: %w", err)
	}
	for _, target := range provisionTargets {
		credential := provisionCredential{target: target, password: secrets[target.role]}
		if err := provisionOne(tx, credential); err != nil {
			return err
		}
	}
	return nil
}

// provisionOne alters one role and verifies every postcondition for it.
func provisionOne(tx *sql.Tx, credential provisionCredential) error {
	role := credential.target.role
	if err := assertRoleExists(tx, credential.target); err != nil {
		return err
	}
	statement, err := buildProvisionStatement(credential)
	if err != nil {
		return fmt.Errorf("provision %s: %w", role, err)
	}
	// nosemgrep: go_sql_rule-concat-sqli -- the role is a compile-time allowlist constant and the verifier is produced by scramSHA256Verifier (base64, $ and : only), so no caller input reaches the string.
	if _, err := tx.Exec(statement); err != nil {
		return fmt.Errorf("provision %s: ALTER ROLE failed: %w", role, err)
	}
	if err := assertSafeRoleAttributes(tx, credential.target); err != nil {
		return err
	}
	if err := assertNoForbiddenRole(tx, credential.target); err != nil {
		return err
	}
	return assertRequiredRoles(tx, credential.target)
}

// assertRoleExists refuses a target that the migrations have not created.
func assertRoleExists(tx *sql.Tx, target provisionTarget) error {
	var exists bool
	if err := tx.QueryRow(
		`SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)`, target.role,
	).Scan(&exists); err != nil {
		return fmt.Errorf("provision %s: look up role: %w", target.role, err)
	}
	if !exists {
		return fmt.Errorf("provision %s: role does not exist; run the migrations first", target.role)
	}
	return nil
}

// buildProvisionStatement returns the only SQL Provision sends. CONNECTION
// LIMIT -1 is set in the same statement, so a provisioned login is usable and
// a not-yet-provisioned login stays at limit 0 regardless of pg_hba.
func buildProvisionStatement(credential provisionCredential) (string, error) {
	if err := validateCapabilityPassword(credential.password); err != nil {
		return "", err
	}
	salt := make([]byte, scramSaltBytes)
	if _, err := rand.Read(salt); err != nil {
		return "", fmt.Errorf("generate salt: %w", err)
	}
	input := scramInput{password: credential.password, salt: salt, iterations: scramIterations}
	literal, err := sqlText{value: scramSHA256Verifier(input)}.quoted()
	if err != nil {
		return "", err
	}
	// #nosec G201 -- the identifier is a fixed role name and the literal is a
	// single-quote-doubled SCRAM verifier; utility statements cannot bind
	// parameters.
	return fmt.Sprintf("ALTER ROLE %s CONNECTION LIMIT -1 PASSWORD %s",
		sqlIdentifier{value: credential.target.role}.quoted(), literal), nil
}

// validateCapabilityPassword rejects anything SASLprep could transform. We do
// not implement stringprep; a non-ASCII or spaced password would derive a
// verifier that never matches, so it is refused with an actionable message.
func validateCapabilityPassword(password string) error {
	if password == "" {
		return errors.New("is required")
	}
	for _, r := range password {
		if r <= ' ' || r > '~' {
			return errors.New("capability passwords must be ASCII without spaces")
		}
	}
	return nil
}

// scramSHA256Verifier builds PostgreSQL's stored SCRAM-SHA-256 secret
// (src/common/scram-common.c, scram_build_secret):
//
//	salted = PBKDF2-HMAC-SHA256(password, salt, iterations, 32)
//	clientKey = HMAC-SHA256(salted, "Client Key")
//	storedKey = SHA256(clientKey)
//	serverKey = HMAC-SHA256(salted, "Server Key")
func scramSHA256Verifier(input scramInput) string {
	salted := pbkdf2.Key([]byte(input.password), input.salt, input.iterations, sha256.Size, sha256.New)
	clientKey := hmacSHA256(salted, []byte("Client Key"))
	storedKey := sha256.Sum256(clientKey)
	serverKey := hmacSHA256(salted, []byte("Server Key"))
	return fmt.Sprintf(
		"SCRAM-SHA-256$%d:%s$%s:%s",
		input.iterations,
		base64.StdEncoding.EncodeToString(input.salt),
		base64.StdEncoding.EncodeToString(storedKey[:]),
		base64.StdEncoding.EncodeToString(serverKey),
	)
}

// hmacSHA256 returns HMAC-SHA256(key, message).
func hmacSHA256(key, message []byte) []byte {
	mac := hmac.New(sha256.New, key)
	mac.Write(message)
	return mac.Sum(nil)
}

// roleAttributes is the safe-role postcondition loaded from pg_roles.
type roleAttributes struct {
	super, bypass, login, inherit, createdb, createrole bool
	connlimit                                           int
	validUntil                                          roleValidUntil
}

// safe reports whether the role is a non-privileged, provisioned login.
func (a roleAttributes) safe(now time.Time) bool {
	return !a.super && !a.bypass && a.login && !a.inherit &&
		!a.createdb && !a.createrole && a.connlimit == -1 && !a.expired(now)
}

// expired reports whether the role has an explicit expiry that has passed.
func (a roleAttributes) expired(now time.Time) bool {
	return a.validUntil.expired(now)
}

// describe renders the attributes for an actionable provisioning error.
func (a roleAttributes) describe() string {
	return fmt.Sprintf(
		"super=%v bypass=%v login=%v inherit=%v createdb=%v createrole=%v connlimit=%d validuntil=%s",
		a.super, a.bypass, a.login, a.inherit, a.createdb, a.createrole, a.connlimit,
		a.validUntil.describe(),
	)
}

// The PostgreSQL timestamp literals for "no expiry" and "expired before any
// timestamp". They are not RFC 3339 and cannot be scanned into time.Time.
const (
	roleValidInfinity = "infinity"
	roleValidNegInf   = "-infinity"
	// roleValidUntilSQL renders `pg_roles.rolvaliduntil` as text with the two
	// sentinels preserved.
	//
	// lib/pq only converts timestamps to time.Time when EnableInfinityTs has
	// been called, and it never is: an operator who runs
	// `ALTER ROLE … VALID UNTIL 'infinity'` otherwise makes a sql.NullTime scan
	// fail with "unsupported Scan, storing driver.Value type []uint8 into type
	// *time.Time". Normalising the column here keeps the two sentinels
	// distinguishable in Go and pins the finite format to UTC, so the Go parser
	// does not depend on the server's TimeZone setting.
	roleValidUntilSQL = `
		SELECT rolsuper, rolbypassrls, rolcanlogin, rolinherit,
		       rolcreatedb, rolcreaterole, rolconnlimit,
		       CASE
		           WHEN rolvaliduntil IS NULL THEN NULL
		           WHEN rolvaliduntil = 'infinity'::timestamptz THEN 'infinity'
		           WHEN rolvaliduntil = '-infinity'::timestamptz THEN '-infinity'
		           ELSE to_char(rolvaliduntil AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
		       END
		FROM pg_roles WHERE rolname = $1`
)

// roleValidUntil is the parsed form of pg_roles.rolvaliduntil. The four states
// are distinct: no expiry at all, an infinite expiry, an expiry before any
// timestamp, and a finite instant.
type roleValidUntil struct {
	// at is the expiry when the value is a finite timestamp.
	at time.Time
	// bounded is true for a finite timestamp in at.
	bounded bool
	// unbounded is PostgreSQL 'infinity': the credential never expires.
	unbounded bool
	// beforeEpoch is PostgreSQL '-infinity': the credential is already expired.
	beforeEpoch bool
}

// parseRoleValidUntil converts the normalised text into a roleValidUntil.
func parseRoleValidUntil(value sql.NullString) (roleValidUntil, error) {
	if !value.Valid || value.String == "" {
		return roleValidUntil{}, nil
	}
	switch value.String {
	case roleValidInfinity:
		return roleValidUntil{unbounded: true}, nil
	case roleValidNegInf:
		return roleValidUntil{beforeEpoch: true}, nil
	}
	at, err := time.Parse(time.RFC3339Nano, value.String)
	if err != nil {
		return roleValidUntil{}, fmt.Errorf("unrecognised rolvaliduntil %q: %w", value.String, err)
	}
	return roleValidUntil{at: at, bounded: true}, nil
}

// expired reports whether the credential's validity has ended by now.
func (v roleValidUntil) expired(now time.Time) bool {
	switch {
	case v.unbounded:
		return false
	case v.beforeEpoch:
		return true
	case v.bounded:
		return !v.at.After(now)
	default:
		return false
	}
}

// describe renders the expiry for an operator-facing provisioning error.
func (v roleValidUntil) describe() string {
	switch {
	case v.unbounded:
		return roleValidInfinity
	case v.beforeEpoch:
		return roleValidNegInf
	case v.bounded:
		return v.at.UTC().Format(time.RFC3339)
	default:
		return "none"
	}
}

// loadRoleAttributes reads the postcondition columns for one role.
func loadRoleAttributes(tx *sql.Tx, target provisionTarget) (roleAttributes, error) {
	var a roleAttributes
	var validUntil sql.NullString
	if err := tx.QueryRow(roleValidUntilSQL, target.role).
		Scan(&a.super, &a.bypass, &a.login, &a.inherit, &a.createdb, &a.createrole,
			&a.connlimit, &validUntil); err != nil {
		return roleAttributes{}, err
	}
	parsed, err := parseRoleValidUntil(validUntil)
	if err != nil {
		return roleAttributes{}, err
	}
	a.validUntil = parsed
	return a, nil
}

// assertSafeRoleAttributes fails closed on a role that is privileged, expired,
// or not a provisioned login.
func assertSafeRoleAttributes(tx *sql.Tx, target provisionTarget) error {
	attributes, err := loadRoleAttributes(tx, target)
	if err != nil {
		return fmt.Errorf("provision %s: verify role: %w", target.role, err)
	}
	if attributes.expired(time.Now()) {
		return fmt.Errorf(
			"provision %s: credential expired at %s; update rolvaliduntil",
			target.role, attributes.describe(),
		)
	}
	if !attributes.safe(time.Now()) {
		return fmt.Errorf("provision %s: unsafe role attributes (%s)", target.role, attributes.describe())
	}
	return nil
}

// assertNoForbiddenRole rejects reachability of a privileged role by any path.
func assertNoForbiddenRole(tx *sql.Tx, target provisionTarget) error {
	for _, forbidden := range target.forbiddenRoles {
		reachable, err := roleReachable(tx, target.role, forbidden)
		if err != nil {
			return fmt.Errorf("provision %s: membership check for %s failed: %w", target.role, forbidden, err)
		}
		if reachable {
			return fmt.Errorf("provision %s: must not reach %s by any path", target.role, forbidden)
		}
	}
	return nil
}

// assertRequiredRoles rejects a login that lost a role it needs.
func assertRequiredRoles(tx *sql.Tx, target provisionTarget) error {
	for _, required := range target.requiredRoles {
		reachable, err := roleReachable(tx, target.role, required)
		if err != nil {
			return fmt.Errorf("provision %s: membership check for %s failed: %w", target.role, required, err)
		}
		if !reachable {
			return fmt.Errorf("provision %s: missing required role %s", target.role, required)
		}
	}
	return nil
}

// roleReachable reports whether role can assume target by any membership path.
func roleReachable(tx *sql.Tx, role, target string) (bool, error) {
	var reachable bool
	err := tx.QueryRow(
		`SELECT pg_has_role($1::name, $2::name, 'MEMBER')`, role, target,
	).Scan(&reachable)
	return reachable, err
}

// resolveProvisionSecrets reads every capability password and enforces the
// safety rules: present, printable ASCII without spaces, pairwise distinct, and
// different from the migration DSN credential.
func resolveProvisionSecrets(getenv func(string) string, owner ownerCredential) (provisionSecrets, error) {
	secrets := make(provisionSecrets, len(provisionTargets))
	seen := make(map[string]string, len(provisionTargets))
	for _, target := range provisionTargets {
		value := getenv(target.envName)
		if err := validateCapabilityPassword(value); err != nil {
			return nil, fmt.Errorf("provision: %s: %w", target.envName, err)
		}
		if value == owner.password {
			return nil, fmt.Errorf("provision: %s must differ from the migration DSN credential", target.envName)
		}
		if previous, ok := seen[value]; ok {
			return nil, fmt.Errorf("provision: %s must differ from %s", target.envName, previous)
		}
		seen[value] = target.envName
		secrets[target.role] = value
	}
	return secrets, nil
}

// validateDSNScheme rejects anything the PostgreSQL driver would not accept.
// The error is generic because the DSN can carry a password.
func validateDSNScheme(dsn string) error {
	parsed, err := url.Parse(dsn)
	if err != nil {
		return errors.New("invalid migration DSN")
	}
	switch strings.ToLower(parsed.Scheme) {
	case "postgres", "postgresql":
		return nil
	default:
		return errors.New("migration DSN must use the postgres or postgresql scheme")
	}
}

// dsnPassword extracts the effective owner credential. lib/pq lets the
// `password` query parameter win over URL userinfo; when both are present and
// differ the DSN is ambiguous and rejected. The errors are generic because the
// DSN can carry the password.
func dsnPassword(dsn string) (string, error) {
	parsed, err := url.Parse(dsn)
	if err != nil {
		return "", errors.New("invalid DSN")
	}
	userInfo, query := dsnCredentials(parsed)
	if ambiguousCredentials(userInfo, query) {
		return "", errors.New("ambiguous DSN credentials")
	}
	if query != "" {
		return query, nil
	}
	if userInfo != "" {
		return userInfo, nil
	}
	return "", errors.New("DSN has no password")
}

// dsnCredentials returns the URL userinfo password and the query password.
func dsnCredentials(parsed *url.URL) (string, string) {
	userInfo := ""
	if parsed.User != nil {
		userInfo, _ = parsed.User.Password()
	}
	return userInfo, parsed.Query().Get("password")
}

// ambiguousCredentials reports two present-and-different credentials.
func ambiguousCredentials(userInfo, query string) bool {
	if userInfo == "" || query == "" {
		return false
	}
	return userInfo != query
}

// sanitizeProvisionError removes the DSN, its credential, and every capability
// secret from a connection or SQL error while keeping non-sensitive context.
func sanitizeProvisionError(err error, run provisionRun) error {
	if err == nil {
		return nil
	}
	message := err.Error()
	if owner, parseErr := dsnPassword(run.dsn); parseErr == nil {
		message = redaction{message: message, secret: owner}.apply()
	}
	for _, secret := range run.secrets {
		message = redaction{message: message, secret: secret}.apply()
	}
	if run.dsn != "" {
		message = strings.ReplaceAll(message, run.dsn, RedactedDSN(run.dsn))
	}
	return errors.New(message)
}

// quoted returns the single-quoted SQL literal for this text.
func (t sqlText) quoted() (string, error) {
	if strings.ContainsRune(t.value, '\x00') {
		return "", errors.New("value contains a NUL byte")
	}
	return "'" + strings.ReplaceAll(t.value, "'", "''") + "'", nil
}

// quoted returns the double-quoted SQL identifier for this value.
func (i sqlIdentifier) quoted() string {
	return `"` + strings.ReplaceAll(i.value, `"`, `""`) + `"`
}

// apply removes the secret and its single-quote-doubled form from the message.
func (r redaction) apply() string {
	if r.secret == "" {
		return r.message
	}
	message := strings.ReplaceAll(r.message, r.secret, "[redacted]")
	if doubled := strings.ReplaceAll(r.secret, "'", "''"); doubled != r.secret {
		message = strings.ReplaceAll(message, doubled, "[redacted]")
	}
	return message
}
