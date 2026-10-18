package budgetledger

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/google/uuid"
)

func TestHashRequestIsStableAndSized(t *testing.T) {
	a := HashRequest([]byte(`{"model":"gpt"}`))
	b := HashRequest([]byte(`{"model":"gpt"}`))
	c := HashRequest([]byte(`{"model":"other"}`))
	if a != b || a == c || len(a) != 64 {
		t.Fatalf("hash=%q stable=%v distinct=%v", a, a == b, a != c)
	}
}

func TestClaimRejectsUnscopedRequests(t *testing.T) {
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, err := NewPostgresLedger(db, 0)
	if err != nil {
		t.Fatal(err)
	}
	key := strings.Repeat("k", 257)
	cases := []struct {
		name string
		p    Principal
		req  ClaimRequest
	}{
		{"missing org", Principal{AgentID: uuid.New()}, ClaimRequest{Key: "k", RequestHash: "h"}},
		{"missing agent", Principal{OrgID: uuid.New()}, ClaimRequest{Key: "k", RequestHash: "h"}},
		{"blank key", Principal{OrgID: uuid.New(), AgentID: uuid.New()}, ClaimRequest{RequestHash: "h"}},
		{"overlong key", Principal{OrgID: uuid.New(), AgentID: uuid.New()}, ClaimRequest{Key: key, RequestHash: "h"}},
		{"blank hash", Principal{OrgID: uuid.New(), AgentID: uuid.New()}, ClaimRequest{Key: "k"}},
		{"negative estimate", Principal{OrgID: uuid.New(), AgentID: uuid.New()}, ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: -1}},
	}
	for _, tc := range cases {
		if _, err := ledger.Claim(context.Background(), tc.p, tc.req); !errors.Is(err, ErrInvalidClaim) {
			t.Fatalf("%s: error=%v want invalid claim", tc.name, err)
		}
	}
}

func TestFinalizeAndReleaseRejectInvalidSettlement(t *testing.T) {
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, err := NewPostgresLedger(db, 0)
	if err != nil {
		t.Fatal(err)
	}
	valid := Reservation{
		ID: uuid.New(), Principal: Principal{OrgID: uuid.New(), AgentID: uuid.New()},
		Key: "k", RequestHash: "h", Version: 1,
	}
	if err := ledger.Finalize(context.Background(), valid, -1, CompletenessComplete); !errors.Is(err, ErrInvalidClaim) {
		t.Fatalf("negative amount: %v", err)
	}
	if err := ledger.Finalize(context.Background(), valid, 1, Completeness("bogus")); !errors.Is(err, ErrInvalidClaim) {
		t.Fatalf("bad completeness: %v", err)
	}
	if err := ledger.Finalize(context.Background(), Reservation{}, 1, CompletenessComplete); !errors.Is(err, ErrInvalidClaim) {
		t.Fatalf("empty reservation: %v", err)
	}
	if err := ledger.Release(context.Background(), Reservation{}); !errors.Is(err, ErrInvalidClaim) {
		t.Fatalf("empty reservation release: %v", err)
	}
}

func TestNewPostgresLedgerRequiresDatabase(t *testing.T) {
	if _, err := NewPostgresLedger(nil, 0); err == nil {
		t.Fatal("nil db accepted")
	}
	ledger, err := NewOptionalPostgresLedger(nil, 0)
	if err != nil || ledger != nil {
		t.Fatalf("optional ledger=%v err=%v want nil,nil", ledger, err)
	}
}

// expectBeginScoped wires the transaction preamble every ledger tx shares.
func expectBeginScoped(mock sqlmock.Sqlmock, orgID uuid.UUID) {
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(orgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`pg_advisory_xact_lock`).WithArgs(orgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
}

// expectBeginSettled wires the transaction preamble for finalize/release.
func expectBeginSettled(mock sqlmock.Sqlmock, orgID uuid.UUID) {
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(orgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
}

func expectNoActivePeriod(mock sqlmock.Sqlmock, orgID uuid.UUID) {
	mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(orgID).
		WillReturnRows(sqlmock.NewRows([]string{"id", "cap_cents", "spent_cents_cached"}))
}

func activePeriodRows(periodID uuid.UUID, cap, spent int64) *sqlmock.Rows {
	return sqlmock.NewRows([]string{"id", "cap_cents", "spent_cents_cached"}).AddRow(periodID, cap, spent)
}

func expectNoReservationRow(mock sqlmock.Sqlmock, org, agent uuid.UUID, key string) {
	mock.ExpectQuery(`FROM ibex_core\.budget_reservations[\s\S]*FOR UPDATE`).WithArgs(org, agent, key).
		WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "lease_expires_at", "version"}))
}

func reservationRows(id uuid.UUID, hash, state string, lease *time.Time, version int64) *sqlmock.Rows {
	return sqlmock.NewRows([]string{"id", "request_hash", "state", "lease_expires_at", "version"}).
		AddRow(id, hash, state, lease, version)
}

func expectActiveHoldSum(mock sqlmock.Sqlmock, org, periodID, exclude uuid.UUID, cents int64) {
	mock.ExpectQuery(`SELECT COALESCE\(SUM\(amount_estimated_cents\), 0\)`).
		WithArgs(org, periodID, exclude).
		WillReturnRows(sqlmock.NewRows([]string{"coalesce"}).AddRow(cents))
}

func TestClaimNoCapSkipsReservation(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	expectBeginScoped(mock, org)
	expectNoActivePeriod(mock, org)
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent},
		ClaimRequest{Key: "k", RequestHash: HashRequest([]byte("k")), EstimatedCents: 10})
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != ClaimNoCap || out.Reservation.ID != uuid.Nil {
		t.Fatalf("outcome=%+v want no_cap without reservation", out)
	}
	assertMockDone(t, mock)
}

func TestClaimFreshOwnsReservation(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, DefaultLease)
	periodID, reservationID := uuid.New(), uuid.New()
	expectBeginScoped(mock, org)
	mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
		WillReturnRows(activePeriodRows(periodID, 10_000, 250))
	expectNoReservationRow(mock, org, agent, "chat:req-1")
	expectActiveHoldSum(mock, org, periodID, uuid.Nil, 300)
	mock.ExpectQuery(`INSERT INTO ibex_core\.budget_reservations`).
		WithArgs(org, agent, periodID, "chat:req-1", HashRequest([]byte("body")), int64(42), "900.000000 seconds").
		WillReturnRows(sqlmock.NewRows([]string{"id", "version"}).AddRow(reservationID, int64(1)))
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent},
		ClaimRequest{Key: "chat:req-1", RequestHash: HashRequest([]byte("body")), EstimatedCents: 42})
	if err != nil {
		t.Fatal(err)
	}
	want := Reservation{
		ID: reservationID, Principal: Principal{OrgID: org, AgentID: agent},
		Key: "chat:req-1", RequestHash: HashRequest([]byte("body")), PeriodID: periodID, Version: 1,
	}
	if out.Kind != ClaimOwned || out.Reservation != want {
		t.Fatalf("outcome=%+v want owned %+v", out, want)
	}
	assertMockDone(t, mock)
}

func TestClaimExceedsCap(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	periodID := uuid.New()
	expectBeginScoped(mock, org)
	mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
		WillReturnRows(activePeriodRows(periodID, 1_000, 100))
	expectNoReservationRow(mock, org, agent, "k")
	expectActiveHoldSum(mock, org, periodID, uuid.Nil, 700)
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent},
		ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 300})
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != ClaimExceeded || out.RemainingCents != 200 {
		t.Fatalf("outcome=%+v want exceeded remaining=200", out)
	}
	assertMockDone(t, mock)
}

func TestClaimConflictOnHashMismatch(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	periodID, reservationID := uuid.New(), uuid.New()
	expectBeginScoped(mock, org)
	mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
		WillReturnRows(activePeriodRows(periodID, 10_000, 0))
	lease := time.Now().UTC().Add(time.Minute)
	mock.ExpectQuery(`FROM ibex_core\.budget_reservations[\s\S]*FOR UPDATE`).WithArgs(org, agent, "k").
		WillReturnRows(reservationRows(reservationID, "other-hash", "claimed", &lease, 3))
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent},
		ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 10})
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != ClaimConflict {
		t.Fatalf("outcome=%+v want conflict", out)
	}
	assertMockDone(t, mock)
}

func TestClaimInProgressWhileLeaseValid(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	periodID, reservationID := uuid.New(), uuid.New()
	expectBeginScoped(mock, org)
	mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
		WillReturnRows(activePeriodRows(periodID, 10_000, 0))
	lease := time.Now().UTC().Add(2 * time.Minute)
	mock.ExpectQuery(`FROM ibex_core\.budget_reservations[\s\S]*FOR UPDATE`).WithArgs(org, agent, "k").
		WillReturnRows(reservationRows(reservationID, "h", "claimed", &lease, 1))
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent},
		ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 10})
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != ClaimInProgress || out.RetryAfter <= 0 {
		t.Fatalf("outcome=%+v want in_progress with retry-after", out)
	}
	assertMockDone(t, mock)
}

func TestClaimReclaimsExpiredLease(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, DefaultLease)
	periodID, reservationID := uuid.New(), uuid.New()
	expectBeginScoped(mock, org)
	mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
		WillReturnRows(activePeriodRows(periodID, 10_000, 0))
	expired := time.Now().UTC().Add(-time.Minute)
	mock.ExpectQuery(`FROM ibex_core\.budget_reservations[\s\S]*FOR UPDATE`).WithArgs(org, agent, "k").
		WillReturnRows(reservationRows(reservationID, "h", "claimed", &expired, 4))
	expectActiveHoldSum(mock, org, periodID, reservationID, 0)
	mock.ExpectQuery(`UPDATE ibex_core\.budget_reservations`).
		WithArgs(periodID, int64(25), "900.000000 seconds", reservationID, org, agent, "k", int64(4)).
		WillReturnRows(sqlmock.NewRows([]string{"id", "version"}).AddRow(reservationID, int64(5)))
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent},
		ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 25})
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != ClaimOwned || out.Reservation.ID != reservationID || out.Reservation.Version != 5 {
		t.Fatalf("outcome=%+v want reclaimed ownership v5", out)
	}
	assertMockDone(t, mock)
}

func TestClaimExpiresStaleHoldWhenCapped(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	periodID, reservationID := uuid.New(), uuid.New()
	expectBeginScoped(mock, org)
	mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
		WillReturnRows(activePeriodRows(periodID, 1_000, 900))
	expired := time.Now().UTC().Add(-time.Minute)
	mock.ExpectQuery(`FROM ibex_core\.budget_reservations[\s\S]*FOR UPDATE`).WithArgs(org, agent, "k").
		WillReturnRows(reservationRows(reservationID, "h", "claimed", &expired, 2))
	expectActiveHoldSum(mock, org, periodID, reservationID, 0)
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).
		WithArgs(reservationID, org, agent, "k", int64(2)).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent},
		ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 500})
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != ClaimExceeded || out.RemainingCents != 100 {
		t.Fatalf("outcome=%+v want exceeded remaining=100", out)
	}
	assertMockDone(t, mock)
}

func TestClaimResetsTerminalRow(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	periodID, reservationID := uuid.New(), uuid.New()
	expectBeginScoped(mock, org)
	mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
		WillReturnRows(activePeriodRows(periodID, 10_000, 0))
	mock.ExpectQuery(`FROM ibex_core\.budget_reservations[\s\S]*FOR UPDATE`).WithArgs(org, agent, "k").
		WillReturnRows(reservationRows(reservationID, "h", "finalized", nil, 9))
	expectActiveHoldSum(mock, org, periodID, reservationID, 0)
	mock.ExpectQuery(`UPDATE ibex_core\.budget_reservations`).
		WithArgs(periodID, int64(25), "900.000000 seconds", reservationID, org, agent, "k", int64(9)).
		WillReturnRows(sqlmock.NewRows([]string{"id", "version"}).AddRow(reservationID, int64(10)))
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent},
		ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 25})
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != ClaimOwned || out.Reservation.Version != 10 {
		t.Fatalf("outcome=%+v want owned v10", out)
	}
	assertMockDone(t, mock)
}

func TestClaimInsertRacedBecomesInProgress(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	periodID := uuid.New()
	expectBeginScoped(mock, org)
	mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
		WillReturnRows(activePeriodRows(periodID, 10_000, 0))
	expectNoReservationRow(mock, org, agent, "k")
	expectActiveHoldSum(mock, org, periodID, uuid.Nil, 0)
	mock.ExpectQuery(`INSERT INTO ibex_core\.budget_reservations`).
		WillReturnRows(sqlmock.NewRows([]string{"id", "version"}))
	mock.ExpectCommit()
	out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent},
		ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 5})
	if err != nil {
		t.Fatal(err)
	}
	if out.Kind != ClaimInProgress || out.RetryAfter != time.Second {
		t.Fatalf("outcome=%+v want defensive in_progress", out)
	}
	assertMockDone(t, mock)
}

func TestFinalizeRecordsSettlement(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	claim := Reservation{ID: uuid.New(), Principal: Principal{OrgID: org, AgentID: agent},
		Key: "k", RequestHash: "h", Version: 3}
	expectBeginSettled(mock, org)
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).
		WithArgs(int64(77), "complete", claim.ID, org, agent, "k", int64(3)).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()
	if err := ledger.Finalize(context.Background(), claim, 77, CompletenessComplete); err != nil {
		t.Fatal(err)
	}
	assertMockDone(t, mock)
}

func TestFinalizeIdempotentRepeat(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	claim := Reservation{ID: uuid.New(), Principal: Principal{OrgID: org, AgentID: agent},
		Key: "k", RequestHash: "h", Version: 3}
	expectBeginSettled(mock, org)
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness`).
		WithArgs(claim.ID, org, agent, "k").
		WillReturnRows(sqlmock.NewRows([]string{"state", "amount_final_cents", "finalized_completeness"}).
			AddRow("finalized", int64(77), "complete"))
	mock.ExpectCommit()
	if err := ledger.Finalize(context.Background(), claim, 77, CompletenessComplete); err != nil {
		t.Fatal(err)
	}
	assertMockDone(t, mock)
}

func TestFinalizeClosedReservation(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	claim := Reservation{ID: uuid.New(), Principal: Principal{OrgID: org, AgentID: agent},
		Key: "k", RequestHash: "h", Version: 3}
	expectBeginSettled(mock, org)
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness`).
		WithArgs(claim.ID, org, agent, "k").
		WillReturnRows(sqlmock.NewRows([]string{"state", "amount_final_cents", "finalized_completeness"}).
			AddRow("claimed", nil, nil))
	mock.ExpectRollback()
	err := ledger.Finalize(context.Background(), claim, 77, CompletenessComplete)
	if !errors.Is(err, ErrClaimClosed) {
		t.Fatalf("error=%v want ErrClaimClosed", err)
	}
	assertMockDone(t, mock)
}

func TestFinalizeMissingRowFailsClosed(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	claim := Reservation{ID: uuid.New(), Principal: Principal{OrgID: org, AgentID: agent},
		Key: "k", RequestHash: "h", Version: 3}
	expectBeginSettled(mock, org)
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness`).
		WithArgs(claim.ID, org, agent, "k").
		WillReturnRows(sqlmock.NewRows([]string{"state", "amount_final_cents", "finalized_completeness"}))
	mock.ExpectRollback()
	if err := ledger.Finalize(context.Background(), claim, 77, CompletenessComplete); !errors.Is(err, ErrClaimClosed) {
		t.Fatalf("error=%v want ErrClaimClosed", err)
	}
	assertMockDone(t, mock)
}

func TestReleaseMarksReleasedAndIsIdempotent(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	claim := Reservation{ID: uuid.New(), Principal: Principal{OrgID: org, AgentID: agent},
		Key: "k", RequestHash: "h", Version: 1}
	expectBeginSettled(mock, org)
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).
		WithArgs(claim.ID, org, agent, "k", int64(1)).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()
	if err := ledger.Release(context.Background(), claim); err != nil {
		t.Fatal(err)
	}
	expectBeginSettled(mock, org)
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness`).
		WithArgs(claim.ID, org, agent, "k").
		WillReturnRows(sqlmock.NewRows([]string{"state", "amount_final_cents", "finalized_completeness"}).
			AddRow("released", nil, nil))
	mock.ExpectCommit()
	if err := ledger.Release(context.Background(), claim); err != nil {
		t.Fatal(err)
	}
	assertMockDone(t, mock)
}

func TestReleaseReclaimedReservationFailsClosed(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	claim := Reservation{ID: uuid.New(), Principal: Principal{OrgID: org, AgentID: agent},
		Key: "k", RequestHash: "h", Version: 1}
	expectBeginSettled(mock, org)
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness`).
		WithArgs(claim.ID, org, agent, "k").
		WillReturnRows(sqlmock.NewRows([]string{"state", "amount_final_cents", "finalized_completeness"}).
			AddRow("claimed", nil, nil))
	mock.ExpectRollback()
	if err := ledger.Release(context.Background(), claim); !errors.Is(err, ErrClaimClosed) {
		t.Fatalf("error=%v want ErrClaimClosed", err)
	}
	assertMockDone(t, mock)
}

func TestValidCompleteness(t *testing.T) {
	if !CompletenessComplete.Valid() || !CompletenessEstimated.Valid() || Completeness("").Valid() {
		t.Fatal("completeness validation drifted from the schema values")
	}
}

func newTestLedger(t *testing.T, lease time.Duration) (sqlmock.Sqlmock, *PostgresLedger, uuid.UUID, uuid.UUID) {
	t.Helper()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, err := NewPostgresLedger(db, lease)
	if err != nil {
		t.Fatal(err)
	}
	return mock, ledger, uuid.New(), uuid.New()
}

func assertMockDone(t *testing.T, mock sqlmock.Sqlmock) {
	t.Helper()
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}
