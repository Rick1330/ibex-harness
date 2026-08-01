package repository

import (
	"database/sql"
	"fmt"
	"testing"
	"time"

	_ "github.com/lib/pq"
)

func TestUnit_NormalizeTokenListLimit(t *testing.T) {
	t.Parallel()
	cases := []struct {
		in, want int
	}{
		{in: 0, want: 50},
		{in: -1, want: 50},
		{in: 101, want: 50},
		{in: 1, want: 1},
		{in: 100, want: 100},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(fmt.Sprintf("%d", tc.in), func(t *testing.T) {
			t.Parallel()
			if got := normalizeTokenListLimit(tc.in); got != tc.want {
				t.Fatalf("normalizeTokenListLimit(%d)=%d want %d", tc.in, got, tc.want)
			}
		})
	}
}

func TestUnit_PaginateTokenMetadata(t *testing.T) {
	t.Parallel()
	ts := time.Date(2024, 6, 1, 12, 0, 0, 0, time.UTC)
	rows := []TokenMetadata{
		{ID: "a", CreatedAt: ts},
		{ID: "b", CreatedAt: ts.Add(-time.Second)},
		{ID: "c", CreatedAt: ts.Add(-2 * time.Second)},
	}

	page, next, err := paginateTokenMetadata(rows, 2)
	if err != nil {
		t.Fatalf("paginate: %v", err)
	}
	if len(page) != 2 || page[0].ID != "a" || page[1].ID != "b" {
		t.Fatalf("page=%v", page)
	}
	wantNext := encodeTokenCursor(rows[1].CreatedAt, "b")
	if next != wantNext {
		t.Fatalf("next=%q want %q", next, wantNext)
	}

	full, next, err := paginateTokenMetadata(rows[:2], 2)
	if err != nil {
		t.Fatalf("paginate exact: %v", err)
	}
	if len(full) != 2 || next != "" {
		t.Fatalf("exact page len=%d next=%q", len(full), next)
	}
}

func TestUnit_RequireTokensRepository(t *testing.T) {
	t.Parallel()

	t.Run("nil db fatals", func(t *testing.T) {
		t.Parallel()
		f := &fatalRecorder{}
		defer func() {
			if recover() == nil {
				t.Fatal("expected Fatalf panic")
			}
			if !f.called {
				t.Fatal("expected Fatalf")
			}
		}()
		_ = RequireTokensRepository(f, nil, nil)
	})

	t.Run("non-nil db", func(t *testing.T) {
		t.Parallel()
		db, err := sql.Open("postgres", "postgres://127.0.0.1:1/unused?sslmode=disable")
		if err != nil {
			t.Fatalf("open: %v", err)
		}
		t.Cleanup(func() { _ = db.Close() })
		repo := RequireTokensRepository(t, db, nil)
		if repo == nil {
			t.Fatal("expected repo")
		}
	})
}

type fatalRecorder struct {
	called bool
}

func (f *fatalRecorder) Helper() {}

func (f *fatalRecorder) Fatalf(string, ...any) {
	f.called = true
	panic("fatal")
}
