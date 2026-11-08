package main

import (
	"bytes"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
)

func mapGetenv(values map[string]string) func(string) string {
	return func(key string) string { return values[key] }
}

func TestLoadBootstrapConfigDefaults(t *testing.T) {
	cfg, err := loadBootstrapConfig(mapGetenv(map[string]string{
		"POSTGRES_DSN": "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable",
	}))
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
	}
	if cfg != want {
		t.Fatalf("defaults = %+v, want %+v", cfg, want)
	}
}

func TestLoadBootstrapConfigOverrides(t *testing.T) {
	cfg, err := loadBootstrapConfig(mapGetenv(map[string]string{
		"POSTGRES_DSN":              "postgres://example",
		"IBEX_BOOTSTRAP_ORG_NAME":   "  Acme  ",
		"IBEX_BOOTSTRAP_ORG_SLUG":   "acme-1",
		"IBEX_BOOTSTRAP_USER_EMAIL": "ops@acme.example",
		"IBEX_BOOTSTRAP_USER_NAME":  "Ops",
		"IBEX_BOOTSTRAP_AGENT_NAME": "Acme Agent",
		"IBEX_BOOTSTRAP_AGENT_SLUG": "acme-agent",
		"IBEX_BOOTSTRAP_PAT_NAME":   "Acme PAT",
	}))
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
	}
	if cfg != want {
		t.Fatalf("overrides = %+v, want %+v", cfg, want)
	}
}

func TestLoadBootstrapConfigValidation(t *testing.T) {
	base := map[string]string{
		"POSTGRES_DSN": "postgres://example",
	}
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
			env := make(map[string]string, len(base))
			for k, v := range base {
				env[k] = v
			}
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
	cfg, err := loadBootstrapConfig(mapGetenv(map[string]string{
		"POSTGRES_DSN":          "postgres://example",
		"IBEX_MEMORY_API_TOKEN": memoryToken,
	}))
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

func TestPrintBootstrapResult(t *testing.T) {
	var out bytes.Buffer
	printBootstrapResult(&out, bootstrapResult{PAT: "ibex_pat_test"})
	printed := out.String()
	if !strings.Contains(printed, "IBEX_BOOTSTRAP_PAT=ibex_pat_test") {
		t.Fatalf("PAT block missing: %s", printed)
	}
	if !strings.Contains(printed, "cannot be recovered") {
		t.Fatalf("recovery warning missing: %s", printed)
	}
}

func TestPrintBootstrapResultAlreadyBootstrapped(t *testing.T) {
	var out bytes.Buffer
	printBootstrapResult(&out, bootstrapResult{AlreadyBootstrapped: true})
	printed := out.String()
	if !strings.Contains(printed, "already bootstrapped") {
		t.Fatalf("idempotent message missing: %s", printed)
	}
	if strings.Contains(printed, "IBEX_BOOTSTRAP_PAT") {
		t.Fatalf("already-bootstrapped output must not contain a PAT block: %s", printed)
	}
}
