package budgetledger

import (
	"context"
	"errors"
	"fmt"
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
	if a != b {
		t.Fatalf("hash not stable: %q vs %q", a, b)
	}
	if a == c {
		t.Fatalf("distinct inputs hashed equally: %q", a)
	}
	if len(a) != 64 {
		t.Fatalf("hash length=%d want 64", len(a))
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

func activePeriodRows(periodID uuid.UUID, capCents, spentCents int64) *sqlmock.Rows {
	return sqlmock.NewRows([]string{"id", "cap_cents", "spent_cents_cached"}).AddRow(periodID, capCents, spentCents)
}

func expectNoReservationRow(mock sqlmock.Sqlmock, org, agent uuid.UUID, key string) {
	mock.ExpectQuery(`FROM ibex_core\.budget_reservations[\s\S]*FOR UPDATE`).WithArgs(org, agent, key).
		WillReturnRows(sqlmock.NewRows([]string{"id", "request_hash", "state", "lease_expires_at", "version"}))
}

type reservationSpec struct {
	id      uuid.UUID
	hash    string
	state   string
	lease   *time.Time
	version int64
}

func reservationRows(spec reservationSpec) *sqlmock.Rows {
	return sqlmock.NewRows([]string{"id", "request_hash", "state", "lease_expires_at", "version"}).
		AddRow(spec.id, spec.hash, spec.state, spec.lease, spec.version)
}

type activeHoldSpec struct {
	org     uuid.UUID
	period  uuid.UUID
	exclude uuid.UUID
	cents   int64
}

func expectActiveHoldSum(mock sqlmock.Sqlmock, spec activeHoldSpec) {
	mock.ExpectQuery(`SELECT COALESCE\(SUM\(amount_estimated_cents\), 0\)`).
		WithArgs(spec.org, spec.period, spec.exclude).
		WillReturnRows(sqlmock.NewRows([]string{"coalesce"}).AddRow(spec.cents))
}

func claimOutcome(t *testing.T, ledger *PostgresLedger, org, agent uuid.UUID, req ClaimRequest) ClaimOutcome {
	t.Helper()
	out, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent}, req)
	if err != nil {
		t.Fatal(err)
	}
	return out
}

func TestClaimNoCapSkipsReservation(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	expectBeginScoped(mock, org)
	expectNoActivePeriod(mock, org)
	mock.ExpectCommit()
	out := claimOutcome(t, ledger, org, agent, ClaimRequest{Key: "k", RequestHash: HashRequest([]byte("k")), EstimatedCents: 10})
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
	expectActiveHoldSum(mock, activeHoldSpec{org: org, period: periodID, exclude: uuid.Nil, cents: 300})
	mock.ExpectQuery(`INSERT INTO ibex_core\.budget_reservations`).
		WithArgs(org, agent, periodID, "chat:req-1", HashRequest([]byte("body")), int64(42), "900.000000 seconds").
		WillReturnRows(sqlmock.NewRows([]string{"id", "version"}).AddRow(reservationID, int64(1)))
	mock.ExpectCommit()
	out := claimOutcome(t, ledger, org, agent, ClaimRequest{Key: "chat:req-1", RequestHash: HashRequest([]byte("body")), EstimatedCents: 42})
	want := Reservation{
		ID: reservationID, Principal: Principal{OrgID: org, AgentID: agent},
		Key: "chat:req-1", RequestHash: HashRequest([]byte("body")), PeriodID: periodID, Version: 1,
	}
	if out.Kind != ClaimOwned || out.Reservation != want {
		t.Fatalf("outcome=%+v want owned %+v", out, want)
	}
	assertMockDone(t, mock)
}

func TestClaimFreshUsesConfiguredLease(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 30*time.Minute)
	periodID, reservationID := uuid.New(), uuid.New()
	expectBeginScoped(mock, org)
	mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
		WillReturnRows(activePeriodRows(periodID, 10_000, 0))
	expectNoReservationRow(mock, org, agent, "k")
	expectActiveHoldSum(mock, activeHoldSpec{org: org, period: periodID, exclude: uuid.Nil, cents: 0})
	mock.ExpectQuery(`INSERT INTO ibex_core\.budget_reservations`).
		WithArgs(org, agent, periodID, "k", "h", int64(5), "1800.000000 seconds").
		WillReturnRows(sqlmock.NewRows([]string{"id", "version"}).AddRow(reservationID, int64(1)))
	mock.ExpectCommit()
	out := claimOutcome(t, ledger, org, agent, ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 5})
	if out.Kind != ClaimOwned {
		t.Fatalf("outcome=%+v want owned", out)
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
	expectActiveHoldSum(mock, activeHoldSpec{org: org, period: periodID, exclude: uuid.Nil, cents: 700})
	mock.ExpectCommit()
	out := claimOutcome(t, ledger, org, agent, ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 300})
	if out.Kind != ClaimExceeded || out.RemainingCents != 200 {
		t.Fatalf("outcome=%+v want exceeded remaining=200", out)
	}
	assertMockDone(t, mock)
}

func TestClaimOverspentPeriodClampsRemainingCents(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	periodID := uuid.New()
	expectBeginScoped(mock, org)
	mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
		WillReturnRows(activePeriodRows(periodID, 100, 500))
	expectNoReservationRow(mock, org, agent, "k")
	expectActiveHoldSum(mock, activeHoldSpec{org: org, period: periodID, exclude: uuid.Nil, cents: 0})
	mock.ExpectCommit()
	out := claimOutcome(t, ledger, org, agent, ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 10})
	if out.Kind != ClaimExceeded || out.RemainingCents != 0 {
		t.Fatalf("outcome=%+v want exceeded remaining=0", out)
	}
	assertMockDone(t, mock)
}

func TestLeaseIntervalDefaultsNonPositive(t *testing.T) {
	want := fmt.Sprintf("%f seconds", DefaultLease.Seconds())
	if got := leaseInterval(0); got != want {
		t.Fatalf("leaseInterval(0)=%q want %q", got, want)
	}
	if got := leaseInterval(-time.Minute); got != want {
		t.Fatalf("leaseInterval(-1m)=%q want %q", got, want)
	}
}

func TestClaimConflictOnHashMismatch(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	periodID, reservationID := uuid.New(), uuid.New()
	expectBeginScoped(mock, org)
	mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
		WillReturnRows(activePeriodRows(periodID, 10_000, 0))
	lease := time.Now().UTC().Add(time.Minute)
	mock.ExpectQuery(`FROM ibex_core\.budget_reservations[\s\S]*FOR UPDATE`).WithArgs(org, agent, "k").
		WillReturnRows(reservationRows(reservationSpec{id: reservationID, hash: "other-hash", state: "claimed", lease: &lease, version: 3}))
	mock.ExpectCommit()
	out := claimOutcome(t, ledger, org, agent, ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 10})
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
		WillReturnRows(reservationRows(reservationSpec{id: reservationID, hash: "h", state: "claimed", lease: &lease, version: 1}))
	mock.ExpectCommit()
	out := claimOutcome(t, ledger, org, agent, ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 10})
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
		WillReturnRows(reservationRows(reservationSpec{id: reservationID, hash: "h", state: "claimed", lease: &expired, version: 4}))
	expectActiveHoldSum(mock, activeHoldSpec{org: org, period: periodID, exclude: reservationID, cents: 0})
	mock.ExpectQuery(`UPDATE ibex_core\.budget_reservations`).
		WithArgs(periodID, int64(25), "900.000000 seconds", reservationID, org, agent, "k", int64(4)).
		WillReturnRows(sqlmock.NewRows([]string{"id", "version"}).AddRow(reservationID, int64(5)))
	mock.ExpectCommit()
	out := claimOutcome(t, ledger, org, agent, ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 25})
	if out.Kind != ClaimOwned {
		t.Fatalf("outcome=%+v want owned", out)
	}
	if out.Reservation.ID != reservationID {
		t.Fatalf("reservation id=%s want %s", out.Reservation.ID, reservationID)
	}
	if out.Reservation.Version != 5 {
		t.Fatalf("version=%d want 5", out.Reservation.Version)
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
		WillReturnRows(reservationRows(reservationSpec{id: reservationID, hash: "h", state: "claimed", lease: &expired, version: 2}))
	expectActiveHoldSum(mock, activeHoldSpec{org: org, period: periodID, exclude: reservationID, cents: 0})
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).
		WithArgs(reservationID, org, agent, "k", int64(2)).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()
	out := claimOutcome(t, ledger, org, agent, ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 500})
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
		WillReturnRows(reservationRows(reservationSpec{id: reservationID, hash: "h", state: "finalized", lease: nil, version: 9}))
	expectActiveHoldSum(mock, activeHoldSpec{org: org, period: periodID, exclude: reservationID, cents: 0})
	mock.ExpectQuery(`UPDATE ibex_core\.budget_reservations`).
		WithArgs(periodID, int64(25), "900.000000 seconds", reservationID, org, agent, "k", int64(9)).
		WillReturnRows(sqlmock.NewRows([]string{"id", "version"}).AddRow(reservationID, int64(10)))
	mock.ExpectCommit()
	out := claimOutcome(t, ledger, org, agent, ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 25})
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
	expectActiveHoldSum(mock, activeHoldSpec{org: org, period: periodID, exclude: uuid.Nil, cents: 0})
	mock.ExpectQuery(`INSERT INTO ibex_core\.budget_reservations`).
		WillReturnRows(sqlmock.NewRows([]string{"id", "version"}))
	mock.ExpectCommit()
	out := claimOutcome(t, ledger, org, agent, ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 5})
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

func settledStateRows() *sqlmock.Rows {
	return sqlmock.NewRows([]string{"state", "amount_final_cents", "finalized_completeness", "version"})
}

func TestFinalizeIdempotentRepeat(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	claim := Reservation{ID: uuid.New(), Principal: Principal{OrgID: org, AgentID: agent},
		Key: "k", RequestHash: "h", Version: 3}
	expectBeginSettled(mock, org)
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness, version`).
		WithArgs(claim.ID, org, agent, "k").
		WillReturnRows(settledStateRows().AddRow("finalized", int64(77), "complete", int64(4)))
	mock.ExpectCommit()
	if err := ledger.Finalize(context.Background(), claim, 77, CompletenessComplete); err != nil {
		t.Fatal(err)
	}
	assertMockDone(t, mock)
}

func TestFinalizeStaleOwnerAfterReclaimFailsClosed(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	claim := Reservation{ID: uuid.New(), Principal: Principal{OrgID: org, AgentID: agent},
		Key: "k", RequestHash: "h", Version: 3}
	expectBeginSettled(mock, org)
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness, version`).
		WithArgs(claim.ID, org, agent, "k").
		WillReturnRows(settledStateRows().AddRow("finalized", int64(77), "complete", int64(5)))
	mock.ExpectRollback()
	err := ledger.Finalize(context.Background(), claim, 77, CompletenessComplete)
	if !errors.Is(err, ErrClaimClosed) {
		t.Fatalf("error=%v want ErrClaimClosed for a newer owner's settlement", err)
	}
	assertMockDone(t, mock)
}

func TestFinalizeMismatchedSettlementFailsClosed(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	claim := Reservation{ID: uuid.New(), Principal: Principal{OrgID: org, AgentID: agent},
		Key: "k", RequestHash: "h", Version: 3}
	expectBeginSettled(mock, org)
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness, version`).
		WithArgs(claim.ID, org, agent, "k").
		WillReturnRows(settledStateRows().AddRow("finalized", int64(78), "complete", int64(4)))
	mock.ExpectRollback()
	err := ledger.Finalize(context.Background(), claim, 77, CompletenessComplete)
	if !errors.Is(err, ErrClaimClosed) {
		t.Fatalf("error=%v want ErrClaimClosed for a mismatched repeat", err)
	}
	assertMockDone(t, mock)
}

func TestFinalizeClosedReservation(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	claim := Reservation{ID: uuid.New(), Principal: Principal{OrgID: org, AgentID: agent},
		Key: "k", RequestHash: "h", Version: 3}
	expectBeginSettled(mock, org)
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness, version`).
		WithArgs(claim.ID, org, agent, "k").
		WillReturnRows(settledStateRows().AddRow("claimed", nil, nil, int64(3)))
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
	mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness, version`).
		WithArgs(claim.ID, org, agent, "k").
		WillReturnRows(settledStateRows())
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
	mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness, version`).
		WithArgs(claim.ID, org, agent, "k").
		WillReturnRows(settledStateRows().AddRow("released", nil, nil, int64(2)))
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
	mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness, version`).
		WithArgs(claim.ID, org, agent, "k").
		WillReturnRows(settledStateRows().AddRow("claimed", nil, nil, int64(2)))
	mock.ExpectRollback()
	if err := ledger.Release(context.Background(), claim); !errors.Is(err, ErrClaimClosed) {
		t.Fatalf("error=%v want ErrClaimClosed", err)
	}
	assertMockDone(t, mock)
}

func TestReleaseStaleOwnerAfterReclaimFailsClosed(t *testing.T) {
	mock, ledger, org, agent := newTestLedger(t, 0)
	claim := Reservation{ID: uuid.New(), Principal: Principal{OrgID: org, AgentID: agent},
		Key: "k", RequestHash: "h", Version: 1}
	expectBeginSettled(mock, org)
	mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness, version`).
		WithArgs(claim.ID, org, agent, "k").
		WillReturnRows(settledStateRows().AddRow("released", nil, nil, int64(3)))
	mock.ExpectRollback()
	if err := ledger.Release(context.Background(), claim); !errors.Is(err, ErrClaimClosed) {
		t.Fatalf("error=%v want ErrClaimClosed for a newer owner's release", err)
	}
	assertMockDone(t, mock)
}

func TestValidCompleteness(t *testing.T) {
	if !CompletenessComplete.Valid() {
		t.Fatal("complete marker rejected")
	}
	if !CompletenessEstimated.Valid() {
		t.Fatal("estimated marker rejected")
	}
	if Completeness("").Valid() {
		t.Fatal("empty completeness accepted")
	}
}

func TestNewOptionalPostgresLedgerBuildsFromDatabase(t *testing.T) {
	t.Parallel()
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ledger, err := NewOptionalPostgresLedger(db, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	if ledger == nil {
		t.Fatal("expected a ledger for a non-nil database")
	}
	if _, ok := ledger.(*PostgresLedger); !ok {
		t.Fatalf("ledger type=%T want *PostgresLedger", ledger)
	}
}

func TestClaimPropagatesDependencyErrors(t *testing.T) {
	t.Parallel()
	req := ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 10}
	cases := []struct {
		name    string
		arrange func(sqlmock.Sqlmock, uuid.UUID, uuid.UUID)
	}{
		{
			name: "begin",
			arrange: func(mock sqlmock.Sqlmock, _, _ uuid.UUID) {
				mock.ExpectBegin().WillReturnError(errors.New("begin failed"))
			},
		},
		{
			name: "org scope",
			arrange: func(mock sqlmock.Sqlmock, org, _ uuid.UUID) {
				mock.ExpectBegin()
				mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).
					WillReturnError(errors.New("scope failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "admission lock",
			arrange: func(mock sqlmock.Sqlmock, org, _ uuid.UUID) {
				mock.ExpectBegin()
				mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).
					WillReturnResult(sqlmock.NewResult(0, 1))
				mock.ExpectExec(`pg_advisory_xact_lock`).WithArgs(org.String()).
					WillReturnError(errors.New("lock failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "active period",
			arrange: func(mock sqlmock.Sqlmock, org, _ uuid.UUID) {
				expectBeginScoped(mock, org)
				mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
					WillReturnError(errors.New("period failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "reservation load",
			arrange: func(mock sqlmock.Sqlmock, org, agent uuid.UUID) {
				expectBeginScoped(mock, org)
				mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
					WillReturnRows(activePeriodRows(uuid.New(), 10_000, 0))
				mock.ExpectQuery(`FROM ibex_core\.budget_reservations[\s\S]*FOR UPDATE`).
					WithArgs(org, agent, "k").
					WillReturnError(errors.New("load failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "fresh holds",
			arrange: func(mock sqlmock.Sqlmock, org, agent uuid.UUID) {
				expectBeginScoped(mock, org)
				mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
					WillReturnRows(activePeriodRows(uuid.New(), 10_000, 0))
				expectNoReservationRow(mock, org, agent, "k")
				mock.ExpectQuery(`SELECT COALESCE`).WithArgs(org, sqlmock.AnyArg(), uuid.Nil).
					WillReturnError(errors.New("holds failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "fresh insert",
			arrange: func(mock sqlmock.Sqlmock, org, agent uuid.UUID) {
				expectBeginScoped(mock, org)
				mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
					WillReturnRows(activePeriodRows(uuid.New(), 10_000, 0))
				expectNoReservationRow(mock, org, agent, "k")
				mock.ExpectQuery(`SELECT COALESCE`).WithArgs(org, sqlmock.AnyArg(), uuid.Nil).
					WillReturnRows(sqlmock.NewRows([]string{"coalesce"}).AddRow(0))
				mock.ExpectQuery(`INSERT INTO ibex_core\.budget_reservations`).
					WillReturnError(errors.New("insert failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "reclaim holds",
			arrange: func(mock sqlmock.Sqlmock, org, agent uuid.UUID) {
				expectBeginScoped(mock, org)
				mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
					WillReturnRows(activePeriodRows(uuid.New(), 10_000, 0))
				expired := time.Now().UTC().Add(-time.Minute)
				mock.ExpectQuery(`FROM ibex_core\.budget_reservations[\s\S]*FOR UPDATE`).
					WithArgs(org, agent, "k").
					WillReturnRows(reservationRows(reservationSpec{
						id: uuid.New(), hash: "h", state: "claimed", lease: &expired, version: 1,
					}))
				mock.ExpectQuery(`SELECT COALESCE`).WithArgs(org, sqlmock.AnyArg(), sqlmock.AnyArg()).
					WillReturnError(errors.New("holds failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "reclaim reset",
			arrange: func(mock sqlmock.Sqlmock, org, agent uuid.UUID) {
				expectBeginScoped(mock, org)
				mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
					WillReturnRows(activePeriodRows(uuid.New(), 10_000, 0))
				expired := time.Now().UTC().Add(-time.Minute)
				mock.ExpectQuery(`FROM ibex_core\.budget_reservations[\s\S]*FOR UPDATE`).
					WithArgs(org, agent, "k").
					WillReturnRows(reservationRows(reservationSpec{
						id: uuid.New(), hash: "h", state: "claimed", lease: &expired, version: 1,
					}))
				mock.ExpectQuery(`SELECT COALESCE`).WithArgs(org, sqlmock.AnyArg(), sqlmock.AnyArg()).
					WillReturnRows(sqlmock.NewRows([]string{"coalesce"}).AddRow(0))
				mock.ExpectQuery(`UPDATE ibex_core\.budget_reservations`).
					WillReturnError(errors.New("reset failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "expire stale",
			arrange: func(mock sqlmock.Sqlmock, org, agent uuid.UUID) {
				expectBeginScoped(mock, org)
				mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
					WillReturnRows(activePeriodRows(uuid.New(), 1_000, 1_000))
				expired := time.Now().UTC().Add(-time.Minute)
				mock.ExpectQuery(`FROM ibex_core\.budget_reservations[\s\S]*FOR UPDATE`).
					WithArgs(org, agent, "k").
					WillReturnRows(reservationRows(reservationSpec{
						id: uuid.New(), hash: "h", state: "claimed", lease: &expired, version: 1,
					}))
				mock.ExpectQuery(`SELECT COALESCE`).WithArgs(org, sqlmock.AnyArg(), sqlmock.AnyArg()).
					WillReturnRows(sqlmock.NewRows([]string{"coalesce"}).AddRow(0))
				mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).
					WillReturnError(errors.New("expire failed"))
				mock.ExpectRollback()
			},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			mock, ledger, org, agent := newTestLedger(t, DefaultLease)
			tc.arrange(mock, org, agent)
			_, err := ledger.Claim(context.Background(), Principal{OrgID: org, AgentID: agent}, req)
			if err == nil {
				t.Fatal("expected a dependency error")
			}
			assertMockDone(t, mock)
		})
	}
}

func TestClaimExceededSkipsExpireForTerminalRow(t *testing.T) {
	t.Parallel()
	mock, ledger, org, agent := newTestLedger(t, DefaultLease)
	periodID, reservationID := uuid.New(), uuid.New()
	expectBeginScoped(mock, org)
	mock.ExpectQuery(`FROM ibex_billing\.budget_periods`).WithArgs(org).
		WillReturnRows(activePeriodRows(periodID, 1_000, 1_000))
	mock.ExpectQuery(`FROM ibex_core\.budget_reservations[\s\S]*FOR UPDATE`).WithArgs(org, agent, "k").
		WillReturnRows(reservationRows(reservationSpec{
			id: reservationID, hash: "h", state: "finalized", lease: nil, version: 7,
		}))
	expectActiveHoldSum(mock, activeHoldSpec{org: org, period: periodID, exclude: reservationID, cents: 0})
	mock.ExpectCommit()
	out := claimOutcome(t, ledger, org, agent, ClaimRequest{Key: "k", RequestHash: "h", EstimatedCents: 10})
	if out.Kind != ClaimExceeded || out.RemainingCents != 0 {
		t.Fatalf("outcome=%+v want exceeded remaining=0", out)
	}
	assertMockDone(t, mock)
}

func TestSettlePropagatesDependencyErrors(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name    string
		arrange func(sqlmock.Sqlmock, uuid.UUID, uuid.UUID, Reservation)
		call    func(*PostgresLedger, Reservation) error
	}{
		{
			name: "finalize exec",
			arrange: func(mock sqlmock.Sqlmock, org, _ uuid.UUID, _ Reservation) {
				expectBeginSettled(mock, org)
				mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).
					WillReturnError(errors.New("exec failed"))
				mock.ExpectRollback()
			},
			call: func(ledger *PostgresLedger, claim Reservation) error {
				return ledger.Finalize(context.Background(), claim, 5, CompletenessComplete)
			},
		},
		{
			name: "finalize rows affected",
			arrange: func(mock sqlmock.Sqlmock, org, _ uuid.UUID, _ Reservation) {
				expectBeginSettled(mock, org)
				mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).
					WillReturnResult(sqlmock.NewErrorResult(errors.New("rows failed")))
				mock.ExpectRollback()
			},
			call: func(ledger *PostgresLedger, claim Reservation) error {
				return ledger.Finalize(context.Background(), claim, 5, CompletenessComplete)
			},
		},
		{
			name: "finalize state load",
			arrange: func(mock sqlmock.Sqlmock, org, agent uuid.UUID, claim Reservation) {
				expectBeginSettled(mock, org)
				mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).
					WillReturnResult(sqlmock.NewResult(0, 0))
				mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness, version`).
					WithArgs(claim.ID, org, agent, "k").
					WillReturnError(errors.New("state failed"))
				mock.ExpectRollback()
			},
			call: func(ledger *PostgresLedger, claim Reservation) error {
				return ledger.Finalize(context.Background(), claim, 5, CompletenessComplete)
			},
		},
		{
			name: "release exec",
			arrange: func(mock sqlmock.Sqlmock, org, _ uuid.UUID, _ Reservation) {
				expectBeginSettled(mock, org)
				mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).
					WillReturnError(errors.New("exec failed"))
				mock.ExpectRollback()
			},
			call: func(ledger *PostgresLedger, claim Reservation) error {
				return ledger.Release(context.Background(), claim)
			},
		},
		{
			name: "release state load",
			arrange: func(mock sqlmock.Sqlmock, org, agent uuid.UUID, claim Reservation) {
				expectBeginSettled(mock, org)
				mock.ExpectExec(`UPDATE ibex_core\.budget_reservations`).
					WillReturnResult(sqlmock.NewResult(0, 0))
				mock.ExpectQuery(`SELECT state, amount_final_cents, finalized_completeness, version`).
					WithArgs(claim.ID, org, agent, "k").
					WillReturnError(errors.New("state failed"))
				mock.ExpectRollback()
			},
			call: func(ledger *PostgresLedger, claim Reservation) error {
				return ledger.Release(context.Background(), claim)
			},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			mock, ledger, org, agent := newTestLedger(t, 0)
			claim := Reservation{ID: uuid.New(), Principal: Principal{OrgID: org, AgentID: agent},
				Key: "k", RequestHash: "h", Version: 3}
			tc.arrange(mock, org, agent, claim)
			if err := tc.call(ledger, claim); err == nil {
				t.Fatal("expected a dependency error")
			}
			assertMockDone(t, mock)
		})
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
