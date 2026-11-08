package bootstrap

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/google/uuid"
)

// bootstrapPATName is the file the profile configures; tests assert on it by
// name inside their own directory.
const bootstrapPATName = "bootstrap.pat"

func mapGetenv(values map[string]string) func(string) string {
	return func(key string) string { return values[key] }
}

// patFileEnv returns a bootstrap environment with a PAT path inside a fresh
// temporary directory.
func patFileEnv(t *testing.T, extra map[string]string) map[string]string {
	t.Helper()
	env := map[string]string{
		"POSTGRES_DSN":            "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable",
		"IBEX_BOOTSTRAP_PAT_FILE": filepath.Join(t.TempDir(), "bootstrap.pat"),
	}
	for key, value := range extra {
		env[key] = value
	}
	return env
}

func TestLoadBootstrapConfigDefaults(t *testing.T) {
	env := patFileEnv(t, nil)
	cfg, err := loadBootstrapConfig(mapGetenv(env))
	if err != nil {
		t.Fatalf("loadBootstrapConfig: %v", err)
	}

	want := bootstrapConfig{
		PostgresDSN: "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable",
		OrgName:     "IBEX Harness",
		OrgSlug:     "ibex",
		UserEmail:   "owner@ibex.local",
		UserName:    "Owner",
		AgentName:   "Default Agent",
		AgentSlug:   "default",
		PATName:     "Bootstrap PAT",
		PATFile:     env["IBEX_BOOTSTRAP_PAT_FILE"],
	}
	if cfg != want {
		t.Fatalf("defaults = %+v, want %+v", cfg, want)
	}
}

func TestLoadBootstrapConfigOverrides(t *testing.T) {
	env := patFileEnv(t, map[string]string{
		"POSTGRES_DSN":              "postgres://example",
		"IBEX_BOOTSTRAP_ORG_NAME":   "  Acme  ",
		"IBEX_BOOTSTRAP_ORG_SLUG":   "acme-1",
		"IBEX_BOOTSTRAP_USER_EMAIL": "ops@acme.example",
		"IBEX_BOOTSTRAP_USER_NAME":  "Ops",
		"IBEX_BOOTSTRAP_AGENT_NAME": "Acme Agent",
		"IBEX_BOOTSTRAP_AGENT_SLUG": "acme-agent",
		"IBEX_BOOTSTRAP_PAT_NAME":   "Acme PAT",
	})
	cfg, err := loadBootstrapConfig(mapGetenv(env))
	if err != nil {
		t.Fatalf("loadBootstrapConfig: %v", err)
	}
	want := bootstrapConfig{
		PostgresDSN: "postgres://example",
		OrgName:     "Acme",
		OrgSlug:     "acme-1",
		UserEmail:   "ops@acme.example",
		UserName:    "Ops",
		AgentName:   "Acme Agent",
		AgentSlug:   "acme-agent",
		PATName:     "Acme PAT",
		PATFile:     env["IBEX_BOOTSTRAP_PAT_FILE"],
	}
	if cfg != want {
		t.Fatalf("overrides = %+v, want %+v", cfg, want)
	}
}

func TestLoadBootstrapConfigValidation(t *testing.T) {
	tests := []struct {
		name    string
		mutate  func(map[string]string)
		wantErr string
	}{
		{
			name:    "missing dsn",
			mutate:  func(env map[string]string) { delete(env, "POSTGRES_DSN") },
			wantErr: "POSTGRES_DSN",
		},
		{
			name:    "blank dsn",
			mutate:  func(env map[string]string) { env["POSTGRES_DSN"] = "   " },
			wantErr: "POSTGRES_DSN",
		},
		{
			name:    "missing pat file",
			mutate:  func(env map[string]string) { delete(env, "IBEX_BOOTSTRAP_PAT_FILE") },
			wantErr: "IBEX_BOOTSTRAP_PAT_FILE",
		},
		{
			name: "pat file in a missing directory",
			mutate: func(env map[string]string) {
				env["IBEX_BOOTSTRAP_PAT_FILE"] = filepath.Join(t.TempDir(), "absent", "bootstrap.pat")
			},
			wantErr: "IBEX_BOOTSTRAP_PAT_FILE",
		},
		{
			name:    "uppercase org slug",
			mutate:  func(env map[string]string) { env["IBEX_BOOTSTRAP_ORG_SLUG"] = "Acme" },
			wantErr: "IBEX_BOOTSTRAP_ORG_SLUG",
		},
		{
			name:    "org slug with space",
			mutate:  func(env map[string]string) { env["IBEX_BOOTSTRAP_ORG_SLUG"] = "acme org" },
			wantErr: "IBEX_BOOTSTRAP_ORG_SLUG",
		},
		{
			name:    "invalid agent slug",
			mutate:  func(env map[string]string) { env["IBEX_BOOTSTRAP_AGENT_SLUG"] = "agent_slug" },
			wantErr: "IBEX_BOOTSTRAP_AGENT_SLUG",
		},
		{
			name:    "invalid email",
			mutate:  func(env map[string]string) { env["IBEX_BOOTSTRAP_USER_EMAIL"] = "owner@localhost" },
			wantErr: "IBEX_BOOTSTRAP_USER_EMAIL",
		},
		{
			name:    "invalid memory service token",
			mutate:  func(env map[string]string) { env["IBEX_MEMORY_API_TOKEN"] = "not-a-pat" },
			wantErr: "IBEX_MEMORY_API_TOKEN",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			env := patFileEnv(t, map[string]string{"POSTGRES_DSN": "postgres://example"})
			tc.mutate(env)

			_, err := loadBootstrapConfig(mapGetenv(env))
			if err == nil || !strings.Contains(err.Error(), tc.wantErr) {
				t.Fatalf("loadBootstrapConfig() error = %v, want error naming %s", err, tc.wantErr)
			}
		})
	}
}

func TestLoadBootstrapConfigAcceptsMemoryServiceToken(t *testing.T) {
	memoryToken := "ibex_pat_11111111-1111-1111-1111-111111111111_" + strings.Repeat("a", 43)
	cfg, err := loadBootstrapConfig(mapGetenv(patFileEnv(t, map[string]string{
		"POSTGRES_DSN":          "postgres://example",
		"IBEX_MEMORY_API_TOKEN": memoryToken,
	})))
	if err != nil {
		t.Fatalf("loadBootstrapConfig: %v", err)
	}
	if cfg.MemoryToken != memoryToken {
		t.Fatalf("MemoryToken = %q, want %q", cfg.MemoryToken, memoryToken)
	}
}

func TestMemoryServiceTokenPermissionsValue(t *testing.T) {
	// MemoryRead (bit 0) | MemoryWrite (bit 1).
	const want int64 = 3
	if got := permissions.MemoryRead | permissions.MemoryWrite; got != want {
		t.Fatalf("memory service permissions = %d, want %d", got, want)
	}
}

func TestBootstrapPermissionsValue(t *testing.T) {
	const want int64 = 35455006347011
	if got := bootstrapPermissions(); got != want {
		t.Fatalf("bootstrapPermissions() = %d, want %d", got, want)
	}
}

func TestPrintBootstrapResultFirstRunNamesPATFileOnly(t *testing.T) {
	var out bytes.Buffer
	const path = "/run/ibex/bootstrap.pat"
	if err := printBootstrapResult(&out, bootstrapResult{
		OrgID:   uuid.New(),
		PATPath: path,
	}); err != nil {
		t.Fatalf("printBootstrapResult: %v", err)
	}
	printed := out.String()
	if strings.Contains(printed, "ibex_pat_") {
		t.Fatalf("summary leaked a PAT: %s", printed)
	}
	if !strings.Contains(printed, "IBEX_BOOTSTRAP_PAT_FILE="+path) {
		t.Fatalf("PAT file path missing: %s", printed)
	}
	if !strings.Contains(printed, "make v1-bootstrap-pat") {
		t.Fatalf("retrieval hint missing: %s", printed)
	}
}

func TestPrintBootstrapResultAlreadyBootstrapped(t *testing.T) {
	var out bytes.Buffer
	if err := printBootstrapResult(&out, bootstrapResult{AlreadyBootstrapped: true}); err != nil {
		t.Fatalf("printBootstrapResult: %v", err)
	}
	printed := out.String()
	if !strings.Contains(printed, "already bootstrapped") {
		t.Fatalf("idempotent message missing: %s", printed)
	}
	if strings.Contains(printed, "IBEX_BOOTSTRAP_PAT") {
		t.Fatalf("already-bootstrapped output must not contain a PAT block: %s", printed)
	}
}

func TestWriteRestrictedFileReplacesPermissiveFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, bootstrapPATName)
	if err := os.WriteFile(path, []byte("stale\n"), 0o644); err != nil {
		t.Fatalf("seed permissive file: %v", err)
	}
	if err := writeRestrictedFile(path, "ibex_pat_test_value"); err != nil {
		t.Fatalf("writeRestrictedFile: %v", err)
	}
	assertPATFile(t, dir, "ibex_pat_test_value\n")
}

func TestWriteRestrictedFileDoesNotFollowSymlink(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "target")
	if err := os.WriteFile(target, []byte("original\n"), 0o600); err != nil {
		t.Fatalf("seed target: %v", err)
	}
	link := filepath.Join(dir, "bootstrap.pat")
	if err := os.Symlink(target, link); err != nil {
		t.Fatalf("create symlink: %v", err)
	}
	t.Chdir(dir)
	if err := writeRestrictedFile(link, "ibex_pat_test_value"); err != nil {
		t.Fatalf("writeRestrictedFile: %v", err)
	}
	data, err := os.ReadFile("target")
	if err != nil {
		t.Fatalf("read target: %v", err)
	}
	if string(data) != "original\n" {
		t.Fatalf("target was overwritten through a symlink: %q", string(data))
	}
	info, err := os.Lstat(link)
	if err != nil {
		t.Fatalf("lstat link: %v", err)
	}
	if !info.Mode().IsRegular() {
		t.Fatalf("destination mode = %v, want a regular file", info.Mode())
	}
}

func TestWriteRestrictedFileRejectsMissingDirectory(t *testing.T) {
	path := filepath.Join(t.TempDir(), "absent", "bootstrap.pat")
	if err := writeRestrictedFile(path, "ibex_pat_test_value"); err == nil {
		t.Fatal("expected an error for a missing parent directory")
	}
}

func TestDeliverBootstrapPATWritesRestrictedFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, bootstrapPATName)
	result := bootstrapResult{OrgID: uuid.New(), PAT: "ibex_pat_test_value"}
	got, err := deliverBootstrapPAT(bootstrapConfig{PATFile: path}, result)
	if err != nil {
		t.Fatalf("deliverBootstrapPAT: %v", err)
	}
	if got.PAT != "" || got.PATPath != path {
		t.Fatalf("result = PAT %q path %q", got.PAT, got.PATPath)
	}
	assertPATFile(t, dir, "ibex_pat_test_value\n")
}

func TestDeliverBootstrapPATWithoutPATKeepsResult(t *testing.T) {
	result := bootstrapResult{OrgID: uuid.New()}
	got, err := deliverBootstrapPAT(bootstrapConfig{PATFile: filepath.Join(t.TempDir(), "p")}, result)
	if err != nil {
		t.Fatalf("deliverBootstrapPAT: %v", err)
	}
	if got.PAT != "" || got.PATPath != "" {
		t.Fatalf("result = PAT %q path %q", got.PAT, got.PATPath)
	}
}

func TestDeliverBootstrapPATWriteFailureIsAnError(t *testing.T) {
	result := bootstrapResult{OrgID: uuid.New(), PAT: "ibex_pat_test_value"}
	_, err := deliverBootstrapPAT(
		bootstrapConfig{PATFile: filepath.Join(t.TempDir(), "missing", "bootstrap.pat")},
		result,
	)
	if err == nil {
		t.Fatal("expected a PAT delivery error")
	}
	if strings.Contains(err.Error(), "ibex_pat_test_value") {
		t.Fatalf("error leaked the PAT: %v", err)
	}
}

func TestRunRejectsMissingConfig(t *testing.T) {
	var stdout, stderr bytes.Buffer
	if code := Run(&stdout, &stderr, mapGetenv(nil)); code != 1 {
		t.Fatalf("Run exit code = %d, want 1", code)
	}
	if !strings.Contains(stderr.String(), "POSTGRES_DSN") {
		t.Fatalf("stderr = %q, want a POSTGRES_DSN error", stderr.String())
	}
	if stdout.Len() != 0 {
		t.Fatalf("stdout = %q, want no output", stdout.String())
	}
}

func TestRunFailsWhenPostgresIsUnreachable(t *testing.T) {
	var stdout, stderr bytes.Buffer
	env := patFileEnv(t, map[string]string{
		"POSTGRES_DSN": "postgres://ibex:ibex@127.0.0.1:1/ibex?sslmode=disable&connect_timeout=1",
	})
	if code := Run(&stdout, &stderr, mapGetenv(env)); code != 1 {
		t.Fatalf("Run exit code = %d, want 1", code)
	}
	if !strings.Contains(stderr.String(), "connect postgres") {
		t.Fatalf("stderr = %q, want a connect error", stderr.String())
	}
}

// assertPATFile enters the test's own temporary directory and reads the PAT by
// its fixed name, so the assertion never builds a path from a variable.
func assertPATFile(t *testing.T, dir, want string) {
	t.Helper()
	t.Chdir(dir)
	data, err := os.ReadFile("bootstrap.pat")
	if err != nil {
		t.Fatalf("read PAT file: %v", err)
	}
	if string(data) != want {
		t.Fatalf("PAT file = %q", string(data))
	}
	info, err := os.Stat("bootstrap.pat")
	if err != nil {
		t.Fatalf("stat PAT file: %v", err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Fatalf("PAT file mode = %o", info.Mode().Perm())
	}
}

func TestWriteRestrictedFileRejectsDirectoryDestination(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bootstrap.pat")
	if err := os.Mkdir(path, 0o700); err != nil {
		t.Fatalf("seed directory: %v", err)
	}
	if err := writeRestrictedFile(path, "ibex_pat_test_value"); err == nil {
		t.Fatal("expected an error when the destination is a directory")
	}
}
