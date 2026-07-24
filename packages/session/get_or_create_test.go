package session

import "testing"

func TestUnit_ShouldRetryUniqueRace(t *testing.T) {
	t.Parallel()
	if shouldRetryUniqueRace(nil, "ext") {
		t.Fatal("nil err should not retry")
	}
	if shouldRetryUniqueRace(ErrDuplicateTurn, "") {
		t.Fatal("empty external_id should not retry")
	}
	if shouldRetryUniqueRace(ErrDuplicateTurn, "ext") {
		t.Fatal("non-pq error should not retry")
	}
}
