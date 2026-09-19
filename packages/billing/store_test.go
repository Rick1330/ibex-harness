package billing

import (
	"context"
	"database/sql"
	"encoding/json"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/google/uuid"
)

func TestNewStore_NilDB(t *testing.T) {
	t.Parallel()
	if _, err := NewStore(nil); err == nil {
		t.Fatal("expected error")
	}
}

func newMockStore(t *testing.T) (*Store, sqlmock.Sqlmock) {
	t.Helper()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	store, err := NewStore(db)
	if err != nil {
		t.Fatal(err)
	}
	return store, mock
}

func expectOrgTxBegin(mock sqlmock.Sqlmock) {
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnResult(sqlmock.NewResult(0, 1))
}

func TestLoadOrg_NilOrgID(t *testing.T) {
	t.Parallel()
	store, _ := newMockStore(t)
	_, err := store.LoadOrg(context.Background(), uuid.Nil)
	if err == nil {
		t.Fatal("expected org_id error")
	}
}

func TestLoadOrg_Happy(t *testing.T) {
	t.Parallel()
	store, mock := newMockStore(t)
	org, periodID, prices := happyLoadFixtures(t)
	expectHappyLoadQueries(mock, org, periodID, prices)

	snap, err := store.LoadOrg(context.Background(), org)
	if err != nil {
		t.Fatal(err)
	}
	assertHappySnapshot(t, snap, periodID)
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func happyLoadFixtures(t *testing.T) (org, periodID uuid.UUID, prices []byte) {
	t.Helper()
	org = uuid.New()
	periodID = uuid.New()
	var err error
	prices, err = json.Marshal([]PriceRow{{
		Provider: "openai", ModelPattern: "gpt-4o*",
		InputCentsPer1k: 100, OutputCentsPer1k: 200,
	}})
	if err != nil {
		t.Fatal(err)
	}
	return org, periodID, prices
}

func expectHappyLoadQueries(mock sqlmock.Sqlmock, org, periodID uuid.UUID, prices []byte) {
	start := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	end := time.Date(2026, 2, 1, 0, 0, 0, 0, time.UTC)
	expectOrgTxBegin(mock)
	mock.ExpectQuery(`budget_periods`).
		WithArgs(org, sqlmock.AnyArg()).
		WillReturnRows(sqlmock.NewRows([]string{
			"id", "cap_cents", "spent_cents_cached", "enforcement_mode", "period_start", "period_end",
		}).AddRow(periodID, int64(1000), int64(100), "hard_cap", start, end))
	mock.ExpectQuery(`rate_cards`).
		WithArgs(org).
		WillReturnRows(sqlmock.NewRows([]string{"version", "prices"}).AddRow(int64(3), prices))
	mock.ExpectCommit()
}

func assertHappySnapshot(t *testing.T, snap BudgetSnapshot, periodID uuid.UUID) {
	t.Helper()
	if !snap.HasHardCap {
		t.Fatal("expected hard cap")
	}
	if snap.PeriodID != periodID {
		t.Fatalf("period=%s want %s", snap.PeriodID, periodID)
	}
	if snap.CapCents != 1000 || snap.SpentCents != 100 {
		t.Fatalf("cap/spent=%d/%d", snap.CapCents, snap.SpentCents)
	}
	if snap.EnforcementMode != EnforcementHardCap {
		t.Fatalf("mode=%s", snap.EnforcementMode)
	}
	if snap.PublishedCard.Version != "3" {
		t.Fatalf("card version=%s", snap.PublishedCard.Version)
	}
	if len(snap.PublishedCard.Prices) != 1 {
		t.Fatalf("prices=%d", len(snap.PublishedCard.Prices))
	}
}

func TestLoadOrg_NoHardCapVariants(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name    string
		prices  any // nil => ErrNoRows on rate_cards; []byte => row
		wantVer string
	}{
		{name: "no card row", prices: nil, wantVer: ""},
		{name: "empty prices json", prices: []byte(`[]`), wantVer: "2"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			store, mock := newMockStore(t)
			org := uuid.New()
			expectOrgTxBegin(mock)
			mock.ExpectQuery(`budget_periods`).
				WithArgs(org, sqlmock.AnyArg()).
				WillReturnError(sql.ErrNoRows)
			if tc.prices == nil {
				mock.ExpectQuery(`rate_cards`).
					WithArgs(org).
					WillReturnError(sql.ErrNoRows)
			} else {
				mock.ExpectQuery(`rate_cards`).
					WithArgs(org).
					WillReturnRows(sqlmock.NewRows([]string{"version", "prices"}).AddRow(int64(2), tc.prices))
			}
			mock.ExpectCommit()
			snap, err := store.LoadOrg(context.Background(), org)
			if err != nil {
				t.Fatal(err)
			}
			if snap.HasHardCap {
				t.Fatal("expected no hard cap")
			}
			if snap.PublishedCard.Version != tc.wantVer || len(snap.PublishedCard.Prices) != 0 {
				t.Fatalf("card=%+v", snap.PublishedCard)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestLoadOrg_BadPricesJSON(t *testing.T) {
	t.Parallel()
	store, mock := newMockStore(t)
	org := uuid.New()
	expectOrgTxBegin(mock)
	mock.ExpectQuery(`budget_periods`).
		WithArgs(org, sqlmock.AnyArg()).
		WillReturnError(sql.ErrNoRows)
	mock.ExpectQuery(`rate_cards`).
		WithArgs(org).
		WillReturnRows(sqlmock.NewRows([]string{"version", "prices"}).AddRow(int64(1), []byte(`{not-json`)))
	mock.ExpectRollback()

	_, err := store.LoadOrg(context.Background(), org)
	if err == nil {
		t.Fatal("expected decode prices error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLoadOrg_BeginTxError(t *testing.T) {
	t.Parallel()
	store, mock := newMockStore(t)
	mock.ExpectBegin().WillReturnError(sql.ErrConnDone)
	_, err := store.LoadOrg(context.Background(), uuid.New())
	if err == nil {
		t.Fatal("expected begin error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLoadOrg_SetConfigError(t *testing.T) {
	t.Parallel()
	store, mock := newMockStore(t)
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnError(sql.ErrConnDone)
	mock.ExpectRollback()
	_, err := store.LoadOrg(context.Background(), uuid.New())
	if err == nil || err.Error() == "" {
		t.Fatalf("expected set_config error, got %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLoadOrg_BudgetQueryError(t *testing.T) {
	t.Parallel()
	store, mock := newMockStore(t)
	org := uuid.New()
	expectOrgTxBegin(mock)
	mock.ExpectQuery(`budget_periods`).
		WithArgs(org, sqlmock.AnyArg()).
		WillReturnError(sql.ErrConnDone)
	mock.ExpectRollback()
	_, err := store.LoadOrg(context.Background(), org)
	if err == nil {
		t.Fatal("expected budget query error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLoadOrg_CommitError(t *testing.T) {
	t.Parallel()
	store, mock := newMockStore(t)
	org, periodID, prices := happyLoadFixtures(t)
	expectOrgTxBegin(mock)
	start := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	end := time.Date(2026, 2, 1, 0, 0, 0, 0, time.UTC)
	mock.ExpectQuery(`budget_periods`).
		WithArgs(org, sqlmock.AnyArg()).
		WillReturnRows(sqlmock.NewRows([]string{
			"id", "cap_cents", "spent_cents_cached", "enforcement_mode", "period_start", "period_end",
		}).AddRow(periodID, int64(1000), int64(100), "hard_cap", start, end))
	mock.ExpectQuery(`rate_cards`).
		WithArgs(org).
		WillReturnRows(sqlmock.NewRows([]string{"version", "prices"}).AddRow(int64(3), prices))
	mock.ExpectCommit().WillReturnError(sql.ErrTxDone)
	_, err := store.LoadOrg(context.Background(), org)
	if err == nil {
		t.Fatal("expected commit error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLoadOrg_RateCardQueryError(t *testing.T) {
	t.Parallel()
	store, mock := newMockStore(t)
	org := uuid.New()
	expectOrgTxBegin(mock)
	mock.ExpectQuery(`budget_periods`).
		WithArgs(org, sqlmock.AnyArg()).
		WillReturnError(sql.ErrNoRows)
	mock.ExpectQuery(`rate_cards`).
		WithArgs(org).
		WillReturnError(sql.ErrConnDone)
	mock.ExpectRollback()
	_, err := store.LoadOrg(context.Background(), org)
	if err == nil {
		t.Fatal("expected rate card query error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}
