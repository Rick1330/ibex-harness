package session

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

func TestLookupEvidenceFence_RejectsNilScope(t *testing.T) {
	store := &PostgresStore{}
	for name, orgID := range map[string]uuid.UUID{"nil org": uuid.Nil, "valid org": uuid.New()} {
		t.Run(name, func(t *testing.T) {
			_, err := store.LookupEvidenceFence(context.Background(), orgID, uuid.Nil)
			if err != ErrEvidenceFenceNotFound {
				t.Fatalf("error=%v want %v", err, ErrEvidenceFenceNotFound)
			}
		})
	}
}
