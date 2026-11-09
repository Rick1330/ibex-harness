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

	_ "github.com/lib/pq"
	"golang.org/x/crypto/pbkdf2"
)

// SCRAM-SHA-256 parameters. PostgreSQL's `psql \password` uses the same
// construction: PBKDF2-HMAC-SHA256 with 4096 iterations and a 16-byte salt.
const (
	scramIterations = 4096
	scramSaltBytes  = 16
)

// provisionTarget pairs a capability login with its environment secret and the
// privileged roles it must not reach by any path. ibex_worker is deliberately
// allowed to reach ibex_purge; ibex_runtime and ibex_bootstrap are not.
type provisionTarget struct {
	role           string
	envName        string
	forbiddenRoles []string
}

var provisionTargets = []provisionTarget{
	{role: "ibex_runtime", envName: "IBEX_RUNTIME_DB_PASSWORD", forbiddenRoles: []string{"ibex_service", "ibex_purge"}},
	{role: "ibex_worker", envName: "IBEX_WORKER_DB_PASSWORD", forbiddenRoles: []string{"ibex_service"}},
	{role: "ibex_bootstrap", envName: "IBEX_BOOTSTRAP_DB_PASSWORD", forbiddenRoles: []string{"ibex_service", "ibex_purge"}},
}

type provisionSecrets map[string]string

// provisionCredential pairs a target with its resolved secret so the worker
// functions take one small struct rather than several strings.
type provisionCredential struct {
	target   provisionTarget
	password string
}

// Provision sets the three capability-login passwords in one transaction and
// refuses to commit unless every role is safe and cannot reach a privileged
// identity. Each statement carries a pre-computed SCRAM-SHA-256 verifier,
// never the plaintext, so a failing statement cannot put the password in the
// server log.
func Provision(dsn string) error {
	ownerPassword, err := dsnPassword(dsn)
	if err != nil {
		return errors.New("provision: cannot determine the owner credential from the migration DSN")
	}
	secrets, err := resolveProvisionSecrets(os.Getenv, ownerPassword)
	if err != nil {
		return err
	}

	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return sanitizeProvisionError(fmt.Errorf("provision: open database: %w", err), dsn, secrets)
	}
	defer db.Close()

	tx, err := db.Begin()
	if err != nil {
		return sanitizeProvisionError(fmt.Errorf("provision: begin: %w", err), dsn, secrets)
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.Exec(`SET LOCAL standard_conforming_strings = on`); err != nil {
		return sanitizeProvisionError(fmt.Errorf("provision: set standard_conforming_strings: %w", err), dsn, secrets)
	}

	for _, target := range provisionTargets {
		credential := provisionCredential{target: target, password: secrets[target.role]}
		if err := provisionOne(tx, credential); err != nil {
			return sanitizeProvisionError(err, dsn, secrets)
		}
	}

	if err := tx.Commit(); err != nil {
		return sanitizeProvisionError(fmt.Errorf("provision: commit: %w", err), dsn, secrets)
	}
	return nil
}

func provisionOne(tx *sql.Tx, credential provisionCredential) error {
	role := credential.target.role
	if err := assertRoleExists(tx, role); err != nil {
		return err
	}
	statement, err := buildProvisionStatement(credential)
	if err != nil {
		return fmt.Errorf("provision %s: %w", role, err)
	}
	if _, err := tx.Exec(statement); err != nil {
		return fmt.Errorf("provision %s: ALTER ROLE failed: %w", role, err)
	}
	if err := assertSafeRoleAttributes(tx, role); err != nil {
		return err
	}
	return assertNoForbiddenRole(tx, credential.target)
}

func assertRoleExists(tx *sql.Tx, role string) error {
	var exists bool
	if err := tx.QueryRow(`SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)`, role).Scan(&exists); err != nil {
		return fmt.Errorf("provision %s: look up role: %w", role, err)
	}
	if !exists {
		return fmt.Errorf("provision %s: role does not exist; run the migrations first", role)
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
	literal, err := quoteLiteral(scramSHA256Verifier(credential.password, salt, scramIterations))
	if err != nil {
		return "", err
	}
	// #nosec G201 -- role name is a fixed identifier and the literal is a
	// single-quote-doubled SCRAM verifier; utility statements cannot bind
	// parameters.
	return fmt.Sprintf("ALTER ROLE %s CONNECTION LIMIT -1 PASSWORD %s",
		quoteIdent(credential.target.role), literal), nil
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
func scramSHA256Verifier(password string, salt []byte, iterations int) string {
	salted := pbkdf2.Key([]byte(password), salt, iterations, sha256.Size, sha256.New)
	clientKey := hmacSHA256(salted, []byte("Client Key"))
	storedKey := sha256.Sum256(clientKey)
	serverKey := hmacSHA256(salted, []byte("Server Key"))
	return fmt.Sprintf(
		"SCRAM-SHA-256$%d:%s$%s:%s",
		iterations,
		base64.StdEncoding.EncodeToString(salt),
		base64.StdEncoding.EncodeToString(storedKey[:]),
		base64.StdEncoding.EncodeToString(serverKey),
	)
}

func hmacSHA256(key, message []byte) []byte {
	mac := hmac.New(sha256.New, key)
	mac.Write(message)
	return mac.Sum(nil)
}

type roleAttributes struct {
	super, bypass, login, inherit, createdb, createrole bool
	connlimit                                           int
}

func (a roleAttributes) safe() bool {
	return !a.super && !a.bypass && a.login && !a.inherit && !a.createdb && !a.createrole && a.connlimit == -1
}

func (a roleAttributes) describe() string {
	return fmt.Sprintf(
		"super=%v bypass=%v login=%v inherit=%v createdb=%v createrole=%v connlimit=%d",
		a.super, a.bypass, a.login, a.inherit, a.createdb, a.createrole, a.connlimit,
	)
}

func loadRoleAttributes(tx *sql.Tx, role string) (roleAttributes, error) {
	var a roleAttributes
	err := tx.QueryRow(`
		SELECT rolsuper, rolbypassrls, rolcanlogin, rolinherit,
		       rolcreatedb, rolcreaterole, rolconnlimit
		FROM pg_roles WHERE rolname = $1`, role).
		Scan(&a.super, &a.bypass, &a.login, &a.inherit, &a.createdb, &a.createrole, &a.connlimit)
	return a, err
}

func assertSafeRoleAttributes(tx *sql.Tx, role string) error {
	attributes, err := loadRoleAttributes(tx, role)
	if err != nil {
		return fmt.Errorf("provision %s: verify role: %w", role, err)
	}
	if !attributes.safe() {
		return fmt.Errorf("provision %s: unsafe role attributes (%s)", role, attributes.describe())
	}
	return nil
}

func assertNoForbiddenRole(tx *sql.Tx, target provisionTarget) error {
	for _, forbidden := range target.forbiddenRoles {
		var reachable bool
		if err := tx.QueryRow(
			`SELECT pg_has_role($1::name, $2::name, 'MEMBER')`, target.role, forbidden,
		).Scan(&reachable); err != nil {
			return fmt.Errorf("provision %s: membership check for %s failed: %w", target.role, forbidden, err)
		}
		if reachable {
			return fmt.Errorf("provision %s: must not reach %s by any path", target.role, forbidden)
		}
	}
	return nil
}

// resolveProvisionSecrets reads the three passwords and enforces the safety
// rules: every secret is present, printable ASCII without spaces, pairwise
// distinct, and different from the migration DSN credential.
func resolveProvisionSecrets(getenv func(string) string, ownerPassword string) (provisionSecrets, error) {
	secrets := make(provisionSecrets, len(provisionTargets))
	seen := make(map[string]string, len(provisionTargets))
	for _, target := range provisionTargets {
		value := getenv(target.envName)
		if err := validateCapabilityPassword(value); err != nil {
			return nil, fmt.Errorf("provision: %s: %w", target.envName, err)
		}
		if value == ownerPassword {
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

// dsnPassword extracts the owner credential from the migration DSN. The error
// is deliberately generic: the DSN can carry the password and must not be
// echoed by a parse failure.
func dsnPassword(dsn string) (string, error) {
	parsed, err := url.Parse(dsn)
	if err != nil {
		return "", errors.New("invalid DSN")
	}
	if parsed.User == nil {
		return "", errors.New("DSN has no user")
	}
	password, ok := parsed.User.Password()
	if !ok || password == "" {
		return "", errors.New("DSN has no password")
	}
	return password, nil
}

// sanitizeProvisionError removes the DSN, its credential, and every capability
// secret (raw and quote-doubled) from a connection or SQL error.
func sanitizeProvisionError(err error, dsn string, secrets provisionSecrets) error {
	if err == nil {
		return nil
	}
	message := err.Error()
	if owner, parseErr := dsnPassword(dsn); parseErr == nil {
		message = redactSecret(message, owner)
	}
	for _, secret := range secrets {
		message = redactSecret(message, secret)
	}
	if dsn != "" {
		message = strings.ReplaceAll(message, dsn, RedactedDSN(dsn))
	}
	return errors.New(message)
}

// quoteLiteral returns a single-quoted SQL string literal. It rejects NUL
// because PostgreSQL text cannot contain it.
func quoteLiteral(value string) (string, error) {
	if strings.ContainsRune(value, '\x00') {
		return "", errors.New("value contains a NUL byte")
	}
	return "'" + strings.ReplaceAll(value, "'", "''") + "'", nil
}

// quoteIdent quotes an identifier. Role names here are constants, but the
// helper keeps the statement safe if the list ever changes.
func quoteIdent(value string) string {
	return `"` + strings.ReplaceAll(value, `"`, `""`) + `"`
}

// redactSecret removes a secret and its single-quote-doubled form.
func redactSecret(message, secret string) string {
	if secret == "" {
		return message
	}
	message = strings.ReplaceAll(message, secret, "[redacted]")
	if doubled := strings.ReplaceAll(secret, "'", "''"); doubled != secret {
		message = strings.ReplaceAll(message, doubled, "[redacted]")
	}
	return message
}

// redactError is the single-secret form used by unit tests and any caller that
// does not have the DSN.
func redactError(err error, secret string) error {
	if err == nil || secret == "" {
		return err
	}
	message := redactSecret(err.Error(), secret)
	if message == err.Error() {
		return err
	}
	return errors.New(message)
}
