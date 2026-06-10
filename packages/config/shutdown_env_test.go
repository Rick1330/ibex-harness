package config_test

import (
	"testing"
	"time"

	ibexconfig "github.com/Rick1330/ibex-harness/packages/config"
)

func TestParseShutdownTimeout_defaultWhenUnset(t *testing.T) {
	t.Parallel()
	got, err := ibexconfig.ParseShutdownTimeout("", 30*time.Second)
	if err != nil || got != 30*time.Second {
		t.Fatalf("got %v err=%v", got, err)
	}
}

func TestParseShutdownTimeout_rejectsNonPositive(t *testing.T) {
	t.Parallel()
	if _, err := ibexconfig.ParseShutdownTimeout("0s", 30*time.Second); err == nil {
		t.Fatal("expected error")
	}
}
