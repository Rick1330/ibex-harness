package main

import (
	"errors"
	"testing"
)

// TestRunRejectsUnknownCommand proves run returns the usage sentinel.
func TestRunRejectsUnknownCommand(t *testing.T) {
	err := run("bogus", 0)
	if !errors.Is(err, errUnknownCommand) {
		t.Fatalf("run(bogus) = %v, want errUnknownCommand", err)
	}
}

// TestExitCodeForUsageErrors proves unknown commands and a missing force
// version keep exit status 2, while other failures stay at 1.
func TestExitCodeForUsageErrors(t *testing.T) {
	if got := exitCode(errUnknownCommand); got != 2 {
		t.Fatalf("exitCode(errUnknownCommand) = %d, want 2", got)
	}
	if got := exitCode(errForceVersion); got != 2 {
		t.Fatalf("exitCode(errForceVersion) = %d, want 2", got)
	}
	if got := exitCode(errors.New("other")); got != 1 {
		t.Fatalf("exitCode(other) = %d, want 1", got)
	}
}
