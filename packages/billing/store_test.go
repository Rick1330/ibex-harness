package billing

import (
	"context"
	"database/sql"
	"encoding/json"
	"strings"
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

func expectOrgTxBegin(mock sqlmock.Sqlmock, org uuid.UUID) {
	mock.ExpectBegin()
	expectTenantPin(mock, org)
}

// expectTenantPin matches the two statements LoadOrg runs before its reads:
// the role pin that makes RLS fire, then the tenant GUC it scopes to.
func expectTenantPin(mock sqlmock.Sqlmock, org uuid.UUID) {
	mock.ExpectExec(`SET LOCAL ROLE ibex_app`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
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
	expectOrgTxBegin(mock, org)
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

// assertZeroSnapshot proves a failed pin cannot be read as a budget result:
// an empty snapshot with HasHardCap=false is exactly what "no cap" looks like.
func assertZeroSnapshot(t *testing.T, snap BudgetSnapshot) {
	t.Helper()
	if snap.HasHardCap || snap.PeriodID != uuid.Nil {
		t.Fatalf("failed pin reported an active period: %+v", snap)
	}
	if snap.CapCents != 0 || snap.SpentCents != 0 {
		t.Fatalf("failed pin returned budget amounts: %+v", snap)
	}
	if snap.PublishedCard.Version != "" || len(snap.PublishedCard.Prices) != 0 {
		t.Fatalf("failed pin returned a card %+v", snap.PublishedCard)
	}
}

func expectNoActiveBudget(mock sqlmock.Sqlmock, org uuid.UUID) {
	mock.ExpectQuery(`budget_periods`).
		WithArgs(org, sqlmock.AnyArg()).
		WillReturnError(sql.ErrNoRows)
}

func expectRateCardPrices(mock sqlmock.Sqlmock, org uuid.UUID, prices any) {
	q := mock.ExpectQuery(`rate_cards`).WithArgs(org)
	if prices == nil {
		q.WillReturnError(sql.ErrNoRows)
		return
	}
	q.WillReturnRows(sqlmock.NewRows([]string{"version", "prices"}).AddRow(int64(2), prices))
}

func runNoHardCapVariant(t *testing.T, prices any, wantVer string) {
	t.Helper()
	store, mock := newMockStore(t)
	org := uuid.New()
	expectOrgTxBegin(mock, org)
	expectNoActiveBudget(mock, org)
	expectRateCardPrices(mock, org, prices)
	mock.ExpectCommit()
	snap, err := store.LoadOrg(context.Background(), org)
	if err != nil {
		t.Fatal(err)
	}
	if snap.HasHardCap {
		t.Fatal("expected no hard cap")
	}
	if snap.PublishedCard.Version != wantVer || len(snap.PublishedCard.Prices) != 0 {
		t.Fatalf("card=%+v", snap.PublishedCard)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLoadOrg_NoHardCapVariants(t *testing.T) {
	t.Parallel()
	t.Run("no card row", func(t *testing.T) {
		t.Parallel()
		runNoHardCapVariant(t, nil, "")
	})
	t.Run("empty prices json", func(t *testing.T) {
		t.Parallel()
		runNoHardCapVariant(t, []byte(`[]`), "2")
	})
}

func TestLoadOrg_RollbackFailures(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name  string
		setup func(sqlmock.Sqlmock, uuid.UUID)
	}{
		{
			name: "bad prices json",
			setup: func(mock sqlmock.Sqlmock, org uuid.UUID) {
				expectNoActiveBudget(mock, org)
				mock.ExpectQuery(`rate_cards`).
					WithArgs(org).
					WillReturnRows(sqlmock.NewRows([]string{"version", "prices"}).AddRow(int64(1), []byte(`{not-json`)))
			},
		},
		{
			name: "budget query",
			setup: func(mock sqlmock.Sqlmock, org uuid.UUID) {
				mock.ExpectQuery(`budget_periods`).
					WithArgs(org, sqlmock.AnyArg()).
					WillReturnError(sql.ErrConnDone)
			},
		},
		{
			name: "rate card query",
			setup: func(mock sqlmock.Sqlmock, org uuid.UUID) {
				expectNoActiveBudget(mock, org)
				mock.ExpectQuery(`rate_cards`).
					WithArgs(org).
					WillReturnError(sql.ErrConnDone)
			},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			store, mock := newMockStore(t)
			org := uuid.New()
			expectOrgTxBegin(mock, org)
			tc.setup(mock, org)
			mock.ExpectRollback()
			_, err := store.LoadOrg(context.Background(), org)
			if err == nil {
				t.Fatal("expected error")
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
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

func TestLoadOrg_RolePinError(t *testing.T) {
	t.Parallel()
	store, mock := newMockStore(t)
	org := uuid.New()
	mock.ExpectBegin()
	mock.ExpectExec(`SET LOCAL ROLE ibex_app`).WillReturnError(sql.ErrConnDone)
	mock.ExpectRollback()

	snap, err := store.LoadOrg(context.Background(), org)
	if err == nil {
		t.Fatal("role-pin failure returned no error; the caller would see an empty snapshot")
	}
	if !strings.Contains(err.Error(), "set tenant role") {
		t.Fatalf("error %q does not identify the tenant-role pin", err)
	}
	assertZeroSnapshot(t, snap)
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLoadOrg_OrgGUCError(t *testing.T) {
	t.Parallel()
	store, mock := newMockStore(t)
	org := uuid.New()
	mock.ExpectBegin()
	mock.ExpectExec(`SET LOCAL ROLE ibex_app`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec(`SELECT set_config`).WillReturnError(sql.ErrConnDone)
	mock.ExpectRollback()

	snap, err := store.LoadOrg(context.Background(), org)
	if err == nil {
		t.Fatal("org-GUC failure returned no error; the caller would see an empty snapshot")
	}
	if !strings.Contains(err.Error(), "set org rls") {
		t.Fatalf("error %q does not identify the org GUC", err)
	}
	assertZeroSnapshot(t, snap)
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLoadOrg_PostPinFailureRollsBack(t *testing.T) {
	t.Parallel()
	store, mock := newMockStore(t)
	org := uuid.New()
	expectOrgTxBegin(mock, org)
	mock.ExpectQuery(`budget_periods`).
		WithArgs(org, sqlmock.AnyArg()).
		WillReturnError(sql.ErrConnDone)
	// No ExpectCommit: committing after the failed read would be an unexpected call.
	mock.ExpectRollback()

	snap, err := store.LoadOrg(context.Background(), org)
	if err == nil {
		t.Fatal("post-pin read failure returned no error")
	}
	assertZeroSnapshot(t, snap)
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestLoadOrg_CommitError(t *testing.T) {
	t.Parallel()
	store, mock := newMockStore(t)
	org, periodID, prices := happyLoadFixtures(t)
	expectOrgTxBegin(mock, org)
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
