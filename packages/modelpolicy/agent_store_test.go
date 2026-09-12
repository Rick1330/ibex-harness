package modelpolicy

import (
	"context"
	"database/sql"
	"testing"

	"github.com/google/uuid"
)

func TestNewAgentStore_NilDB(t *testing.T) {
	t.Parallel()
	_, err := NewAgentStore(nil)
	if err == nil {
		t.Fatal("expected error for nil db")
	}
}

func TestNoopAgentDefaults_LoadEmpty(t *testing.T) {
	t.Parallel()
	got, err := NoopAgentDefaults{}.Load(context.Background(), uuid.New(), uuid.New())
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if got.DefaultModel != "" || got.DefaultProvider != "" {
		t.Fatalf("got=%+v want empty", got)
	}
}

func TestNullStr(t *testing.T) {
	t.Parallel()
	if got := nullStr(sql.NullString{}); got != "" {
		t.Fatalf("invalid null: %q", got)
	}
	if got := nullStr(sql.NullString{String: "gpt-4o", Valid: true}); got != "gpt-4o" {
		t.Fatalf("valid: %q", got)
	}
}
