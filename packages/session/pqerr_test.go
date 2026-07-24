package session

import "testing"

func TestUnit_IsUniqueViolation(t *testing.T) {
	t.Parallel()
	if isUniqueViolation(nil) {
		t.Fatal("nil should not be unique violation")
	}
	if isUniqueViolation(ErrDuplicateTurn) {
		t.Fatal("sentinel should not match pq unique")
	}
}

func TestUnit_StatusConstants(t *testing.T) {
	t.Parallel()
	want := map[string]string{
		"active": StatusActive, "completed": StatusCompleted,
		"abandoned": StatusAbandoned, "error": StatusError,
	}
	for k, v := range want {
		if k != v {
			t.Fatalf("status %q != %q", k, v)
		}
	}
}
