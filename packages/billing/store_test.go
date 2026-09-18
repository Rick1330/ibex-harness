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

func TestLoadOrg_NilOrgID(t *testing.T) {
	t.Parallel()
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	store, err := NewStore(db)
	if err != nil {
		t.Fatal(err)
	}
	_, err = store.LoadOrg(context.Background(), uuid.Nil)
	if err == nil {
		t.Fatal("expected org_id error")
	}
}

func TestLoadOrg_Happy(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	store, err := NewStore(db)
	if err != nil {
		t.Fatal(err)
	}

	org := uuid.New()
	periodID := uuid.New()
	start := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	end := time.Date(2026, 2, 1, 0, 0, 0, 0, time.UTC)
	prices, err := json.Marshal([]PriceRow{{
		Provider: "openai", ModelPattern: "gpt-4o*",
		InputCentsPer1k: 100, OutputCentsPer1k: 200,
	}})
	if err != nil {
		t.Fatal(err)
	}

	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`budget_periods`).
		WithArgs(org, sqlmock.AnyArg()).
		WillReturnRows(sqlmock.NewRows([]string{
			"id", "cap_cents", "spent_cents_cached", "enforcement_mode", "period_start", "period_end",
		}).AddRow(periodID, int64(1000), int64(100), "hard_cap", start, end))
	mock.ExpectQuery(`rate_cards`).
		WithArgs(org).
		WillReturnRows(sqlmock.NewRows([]string{"version", "prices"}).AddRow(int64(3), prices))
	mock.ExpectCommit()

	snap, err := store.LoadOrg(context.Background(), org)
	if err != nil {
		t.Fatal(err)
	}
	if !snap.HasHardCap || snap.PeriodID != periodID || snap.CapCents != 1000 || snap.SpentCents != 100 {
		t.Fatalf("snap=%+v", snap)
	}
	if snap.EnforcementMode != EnforcementHardCap {
		t.Fatalf("mode=%s", snap.EnforcementMode)
	}
	if snap.PublishedCard.Version != "3" || len(snap.PublishedCard.Prices) != 1 {
		t.Fatalf("card=%+v", snap.PublishedCard)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLoadOrg_NoHardCapNoCard(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	store, err := NewStore(db)
	if err != nil {
		t.Fatal(err)
	}

	org := uuid.New()
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`budget_periods`).
		WithArgs(org, sqlmock.AnyArg()).
		WillReturnError(sql.ErrNoRows)
	mock.ExpectQuery(`rate_cards`).
		WithArgs(org).
		WillReturnError(sql.ErrNoRows)
	mock.ExpectCommit()

	snap, err := store.LoadOrg(context.Background(), org)
	if err != nil {
		t.Fatal(err)
	}
	if snap.HasHardCap {
		t.Fatal("expected no hard cap")
	}
	if snap.PublishedCard.Version != "" || len(snap.PublishedCard.Prices) != 0 {
		t.Fatalf("card=%+v", snap.PublishedCard)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLoadOrg_BadPricesJSON(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	store, err := NewStore(db)
	if err != nil {
		t.Fatal(err)
	}

	org := uuid.New()
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`budget_periods`).
		WithArgs(org, sqlmock.AnyArg()).
		WillReturnError(sql.ErrNoRows)
	mock.ExpectQuery(`rate_cards`).
		WithArgs(org).
		WillReturnRows(sqlmock.NewRows([]string{"version", "prices"}).AddRow(int64(1), []byte(`{not-json`)))
	mock.ExpectRollback()

	_, err = store.LoadOrg(context.Background(), org)
	if err == nil {
		t.Fatal("expected decode prices error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}
