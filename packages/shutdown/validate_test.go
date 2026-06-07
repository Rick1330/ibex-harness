package shutdown

import (
	"testing"
	"time"
)

func TestValidateTimeout_rejectsZero(t *testing.T) {
	if err := ValidateTimeout(0); err == nil {
		t.Fatal("expected error for zero timeout")
	}
}

func TestValidateTimeout_acceptsPositive(t *testing.T) {
	if err := ValidateTimeout(30 * time.Second); err != nil {
		t.Fatalf("ValidateTimeout: %v", err)
	}
}
