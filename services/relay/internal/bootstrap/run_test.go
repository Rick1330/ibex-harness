package bootstrap

import "testing"

func TestRun_GateOffReturnsZero(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_RELAY_ENABLED", "false")
	if code := Run([]string{"relay"}); code != 0 {
		t.Fatalf("Run with gate off must return 0, got %d", code)
	}
}

func TestRunBootstrap_DisabledExitsCleanly(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_RELAY_ENABLED", "false")
	if code := runBootstrap(nil, nil); code != 0 {
		t.Fatalf("disabled gate must exit 0, got %d", code)
	}
}

func TestRunBootstrap_EnabledWithoutDSNsFailsClosed(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_RELAY_ENABLED", "true")
	t.Setenv("IBEX_RELAY_POSTGRES_DSN", "")
	t.Setenv("IBEX_RELAY_CLICKHOUSE_DSN", "")
	if code := runBootstrap(nil, nil); code != 1 {
		t.Fatalf("missing DSNs must fail closed, got %d", code)
	}
}

func TestRunBootstrap_UnreachablePostgresFailsClosed(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_RELAY_ENABLED", "true")
	t.Setenv("IBEX_RELAY_POSTGRES_DSN", "postgres://relay:pw@127.0.0.1:1/ibex?sslmode=disable")
	t.Setenv("IBEX_RELAY_CLICKHOUSE_DSN", "clickhouse://ibex:ibex@127.0.0.1:1/ibex")
	t.Setenv("IBEX_RELAY_OPERATION_TIMEOUT", "1s")
	if code := runBootstrap(nil, nil); code != 1 {
		t.Fatalf("unreachable postgres must fail closed, got %d", code)
	}
}
