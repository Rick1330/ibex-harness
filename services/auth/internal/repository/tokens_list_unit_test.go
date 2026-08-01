package repository

import (
	"database/sql"
	"fmt"
	"testing"
	"time"

	// Register the postgres driver so sql.Open("postgres", ...) can return a non-nil
	// *sql.DB in unit tests that never dial the network.
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
	rows := sampleTokenMetadataRows()

	t.Run("overflow yields next cursor", func(t *testing.T) {
		t.Parallel()
		assertPaginateOverflow(t, rows)
	})
	t.Run("exact page has empty next", func(t *testing.T) {
		t.Parallel()
		assertPaginateExact(t, rows[:2])
	})
}

func sampleTokenMetadataRows() []TokenMetadata {
	ts := time.Date(2024, 6, 1, 12, 0, 0, 0, time.UTC)
	return []TokenMetadata{
		{ID: "a", CreatedAt: ts},
		{ID: "b", CreatedAt: ts.Add(-time.Second)},
		{ID: "c", CreatedAt: ts.Add(-2 * time.Second)},
	}
}

func assertPaginateOverflow(t *testing.T, rows []TokenMetadata) {
	t.Helper()
	page, next, err := paginateTokenMetadata(rows, 2)
	if err != nil {
		t.Fatalf("paginate: %v", err)
	}
	assertTokenPageIDs(t, page, "a", "b")
	wantNext := encodeTokenCursor(rows[1].CreatedAt, "b")
	if next != wantNext {
		t.Fatalf("next=%q want %q", next, wantNext)
	}
}

func assertTokenPageIDs(t *testing.T, page []TokenMetadata, id0, id1 string) {
	t.Helper()
	if len(page) != 2 {
		t.Fatalf("len=%d want 2 page=%v", len(page), page)
	}
	if page[0].ID != id0 {
		t.Fatalf("page[0]=%q want %q", page[0].ID, id0)
	}
	if page[1].ID != id1 {
		t.Fatalf("page[1]=%q want %q", page[1].ID, id1)
	}
}

func assertPaginateExact(t *testing.T, rows []TokenMetadata) {
	t.Helper()
	full, next, err := paginateTokenMetadata(rows, 2)
	if err != nil {
		t.Fatalf("paginate exact: %v", err)
	}
	if len(full) != 2 {
		t.Fatalf("exact page len=%d", len(full))
	}
	if next != "" {
		t.Fatalf("exact next=%q", next)
	}
}

func TestUnit_RequireTokensRepository(t *testing.T) {
	t.Parallel()

	t.Run("nil db fatals", func(t *testing.T) {
		t.Parallel()
		assertRequireTokensRepositoryFatals(t)
	})

	t.Run("non-nil db", func(t *testing.T) {
		t.Parallel()
		assertRequireTokensRepositoryOK(t)
	})
}

func assertRequireTokensRepositoryFatals(t *testing.T) {
	t.Helper()
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
}

func assertRequireTokensRepositoryOK(t *testing.T) {
	t.Helper()
	db, err := sql.Open("postgres", "postgres://127.0.0.1:1/unused?sslmode=disable")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	repo := RequireTokensRepository(t, db, nil)
	if repo == nil {
		t.Fatal("expected repo")
	}
}

type fatalRecorder struct {
	called bool
}

func (f *fatalRecorder) Helper() {}

func (f *fatalRecorder) Fatalf(string, ...any) {
	f.called = true
	panic("fatal")
}
