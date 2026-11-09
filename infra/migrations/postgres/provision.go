package postgres

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"errors"
	"fmt"
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

// provisionTarget pairs a capability login with the environment variable that
// carries its password. The roles are created by 000064 without a password and
// stay inert until Provision sets one.
type provisionTarget struct {
	role    string
	envName string
}

var provisionTargets = []provisionTarget{
	{role: "ibex_runtime", envName: "IBEX_RUNTIME_DB_PASSWORD"},
	{role: "ibex_worker", envName: "IBEX_WORKER_DB_PASSWORD"},
	{role: "ibex_bootstrap", envName: "IBEX_BOOTSTRAP_DB_PASSWORD"},
}

// Provision sets the three capability-login passwords in one transaction and
// refuses to commit unless every role is still a safe, login-capable role.
//
// Each statement carries a pre-computed SCRAM-SHA-256 verifier, never the
// plaintext: PostgreSQL can log a failing statement at the default
// `log_min_error_statement = error`, and the plaintext must not reach the
// server log.
func Provision(dsn string) error {
	return provisionWithGetter(dsn, os.Getenv)
}

func provisionWithGetter(dsn string, getenv func(string) string) error {
	secrets, err := resolveProvisionSecrets(getenv)
	if err != nil {
		return err
	}

	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return fmt.Errorf("provision: open database: %w", err)
	}
	defer db.Close()

	tx, err := db.Begin()
	if err != nil {
		return fmt.Errorf("provision: begin: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	// Standard-conforming strings keep the verifier literal unambiguous; the
	// verifier itself contains only base64, `$`, `:`, and `-`.
	if _, err := tx.Exec(`SET LOCAL standard_conforming_strings = on`); err != nil {
		return fmt.Errorf("provision: set standard_conforming_strings: %w", err)
	}

	for _, target := range provisionTargets {
		if err := provisionOne(tx, target, secrets[target.role]); err != nil {
			return redactError(err, secrets[target.role])
		}
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("provision: commit: %w", err)
	}
	return nil
}

func provisionOne(tx *sql.Tx, target provisionTarget, secret string) error {
	var exists bool
	if err := tx.QueryRow(`SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)`, target.role).Scan(&exists); err != nil {
		return fmt.Errorf("provision %s: look up role: %w", target.role, err)
	}
	if !exists {
		return fmt.Errorf("provision %s: role does not exist; run the migrations first", target.role)
	}

	stmt, err := buildProvisionStatement(target.role, secret)
	if err != nil {
		return fmt.Errorf("provision %s: build statement: %w", target.role, err)
	}
	if _, err := tx.Exec(stmt); err != nil {
		return fmt.Errorf("provision %s: ALTER ROLE failed: %w", target.role, err)
	}

	var rolsuper, rolbypassrls, rolcanlogin, rolinherit, rolcreatedb, rolcreaterole bool
	var rolconnlimit int
	if err := tx.QueryRow(
		`SELECT rolsuper, rolbypassrls, rolcanlogin, rolinherit, rolcreatedb, rolcreaterole, rolconnlimit
		 FROM pg_roles WHERE rolname = $1`,
		target.role,
	).Scan(&rolsuper, &rolbypassrls, &rolcanlogin, &rolinherit, &rolcreatedb, &rolcreaterole, &rolconnlimit); err != nil {
		return fmt.Errorf("provision %s: verify role: %w", target.role, err)
	}
	if rolsuper || rolbypassrls || !rolcanlogin || rolinherit || rolcreatedb || rolcreaterole || rolconnlimit != -1 {
		return fmt.Errorf(
			"provision %s: unsafe role attributes (rolsuper=%v rolbypassrls=%v rolcanlogin=%v "+
				"rolinherit=%v rolcreatedb=%v rolcreaterole=%v rolconnlimit=%d)",
			target.role, rolsuper, rolbypassrls, rolcanlogin, rolinherit, rolcreatedb, rolcreaterole, rolconnlimit,
		)
	}
	return nil
}

// buildProvisionStatement returns the only SQL Provision sends. The password
// appears only as a SCRAM verifier; the plaintext is not in the statement.
// CONNECTION LIMIT -1 is set in the same statement, so a provisioned login is
// usable and a not-yet-provisioned login stays at limit 0 regardless of pg_hba.
func buildProvisionStatement(role, password string) (string, error) {
	if strings.ContainsRune(password, '\x00') {
		return "", errors.New("password contains a NUL byte")
	}
	if password == "" {
		return "", errors.New("password is empty")
	}
	salt := make([]byte, scramSaltBytes)
	if _, err := rand.Read(salt); err != nil {
		return "", fmt.Errorf("generate salt: %w", err)
	}
	literal, err := quoteLiteral(scramSHA256Verifier(password, salt, scramIterations))
	if err != nil {
		return "", err
	}
	// #nosec G201 -- role name is a fixed identifier and the literal is a
	// single-quote-doubled SCRAM verifier; utility statements cannot bind
	// parameters.
	return fmt.Sprintf("ALTER ROLE %s CONNECTION LIMIT -1 PASSWORD %s", quoteIdent(role), literal), nil
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

// resolveProvisionSecrets reads the three passwords and enforces the safety
// rules: every secret must be present, pairwise distinct, and different from
// the owner password.
func resolveProvisionSecrets(getenv func(string) string) (map[string]string, error) {
	ownerPassword := getenv("POSTGRES_PASSWORD")
	secrets := make(map[string]string, len(provisionTargets))
	seen := make(map[string]string, len(provisionTargets))
	for _, target := range provisionTargets {
		value := getenv(target.envName)
		if strings.TrimSpace(value) == "" {
			return nil, fmt.Errorf("provision: %s is required", target.envName)
		}
		if strings.ContainsRune(value, '\x00') {
			return nil, fmt.Errorf("provision: %s contains a NUL byte", target.envName)
		}
		if ownerPassword != "" && value == ownerPassword {
			return nil, fmt.Errorf("provision: %s must differ from POSTGRES_PASSWORD", target.envName)
		}
		if previous, ok := seen[value]; ok {
			return nil, fmt.Errorf("provision: %s must differ from %s", target.envName, previous)
		}
		seen[value] = target.envName
		secrets[target.role] = value
	}
	return secrets, nil
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

// redactError removes a secret, and its single-quote-doubled form, from an
// error string before it can reach a terminal or a log. The statement no longer
// contains the plaintext, but this is the belt to the verifier's braces.
func redactError(err error, secret string) error {
	if err == nil || secret == "" {
		return err
	}
	msg := err.Error()
	redacted := strings.ReplaceAll(msg, secret, "[redacted]")
	if doubled := strings.ReplaceAll(secret, "'", "''"); doubled != secret {
		redacted = strings.ReplaceAll(redacted, doubled, "[redacted]")
	}
	if redacted == msg {
		return err
	}
	return errors.New(redacted)
}
