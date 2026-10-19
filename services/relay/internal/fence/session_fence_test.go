package fence

import (
	"context"
	"errors"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/google/uuid"
)

func newTestChecker(t *testing.T) (*SessionFenceChecker, sqlmock.Sqlmock) {
	t.Helper()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	checker, err := NewSessionFenceChecker(db, ibexmetrics.NewRelay("test-relay"))
	if err != nil {
		t.Fatal(err)
	}
	return checker, mock
}

func sessionFence(resourceID string) evidenceoutbox.TombstoneFence {
	return evidenceoutbox.TombstoneFence{
		ResourceType: SessionResourceType, ResourceID: resourceID, ResourceVersion: 3,
	}
}

func expectFenceQuery(mock sqlmock.Sqlmock, outcome string) {
	mock.ExpectQuery(`evidence_outbox_check_session_fence`).
		WithArgs(sqlmock.AnyArg(), sqlmock.AnyArg(), int64(3)).
		WillReturnRows(sqlmock.NewRows([]string{"outcome"}).AddRow(outcome))
}

func TestCheckFence_Alive(t *testing.T) {
	checker, mock := newTestChecker(t)
	id := uuid.New()
	expectFenceQuery(mock, "alive")
	if err := checker.CheckFence(context.Background(), uuid.New(), sessionFence(id.String())); err != nil {
		t.Fatalf("alive fence must pass: %v", err)
	}
}

func TestCheckFence_TerminalOutcomes(t *testing.T) {
	for _, outcome := range []string{"tombstoned", "stale_version", "not_found"} {
		t.Run(outcome, func(t *testing.T) {
			checker, mock := newTestChecker(t)
			expectFenceQuery(mock, outcome)
			err := checker.CheckFence(context.Background(), uuid.New(), sessionFence(uuid.New().String()))
			if !errors.Is(err, evidenceoutbox.ErrTombstonedResource) {
				t.Fatalf("outcome %s: want ErrTombstonedResource, got %v", outcome, err)
			}
		})
	}
}

func TestCheckFence_UnsupportedResourceType(t *testing.T) {
	checker, _ := newTestChecker(t)
	f := sessionFence(uuid.New().String())
	f.ResourceType = "memory"
	err := checker.CheckFence(context.Background(), uuid.New(), f)
	if !errors.Is(err, evidenceoutbox.ErrUnsupportedFenceResource) {
		t.Fatalf("want ErrUnsupportedFenceResource, got %v", err)
	}
	if errors.Is(err, evidenceoutbox.ErrTombstonedResource) {
		t.Fatal("unsupported type must not be classified as tombstoned")
	}
}

func TestCheckFence_MalformedIdentity(t *testing.T) {
	checker, _ := newTestChecker(t)
	for name, f := range map[string]evidenceoutbox.TombstoneFence{
		"bad_uuid":     sessionFence("not-a-uuid"),
		"nil_uuid":     sessionFence(uuid.Nil.String()),
		"zero_version": {ResourceType: SessionResourceType, ResourceID: uuid.New().String()},
		"empty_type":   {ResourceID: uuid.New().String(), ResourceVersion: 1},
	} {
		t.Run(name, func(t *testing.T) {
			err := checker.CheckFence(context.Background(), uuid.New(), f)
			if !errors.Is(err, evidenceoutbox.ErrUnsupportedFenceResource) {
				t.Fatalf("want ErrUnsupportedFenceResource, got %v", err)
			}
		})
	}
}

func TestCheckFence_DatabaseErrorIsRetryable(t *testing.T) {
	checker, mock := newTestChecker(t)
	mock.ExpectQuery(`evidence_outbox_check_session_fence`).
		WithArgs(sqlmock.AnyArg(), sqlmock.AnyArg(), int64(3)).
		WillReturnError(errors.New("connection refused"))
	err := checker.CheckFence(context.Background(), uuid.New(), sessionFence(uuid.New().String()))
	if err == nil {
		t.Fatal("db error must surface")
	}
	if errors.Is(err, evidenceoutbox.ErrTombstonedResource) || errors.Is(err, evidenceoutbox.ErrUnsupportedFenceResource) {
		t.Fatalf("db error must stay retryable, got %v", err)
	}
}

func TestCheckFence_UnexpectedOutcomeIsRetryable(t *testing.T) {
	checker, mock := newTestChecker(t)
	expectFenceQuery(mock, "banana")
	err := checker.CheckFence(context.Background(), uuid.New(), sessionFence(uuid.New().String()))
	if err == nil {
		t.Fatal("unexpected outcome must error")
	}
	if errors.Is(err, evidenceoutbox.ErrTombstonedResource) || errors.Is(err, evidenceoutbox.ErrUnsupportedFenceResource) {
		t.Fatalf("unexpected outcome must stay retryable, got %v", err)
	}
}

func TestNewSessionFenceChecker_RequiresDependencies(t *testing.T) {
	if _, err := NewSessionFenceChecker(nil, ibexmetrics.NewRelay("test-relay")); err == nil {
		t.Fatal("nil db must be rejected")
	}
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	if _, err := NewSessionFenceChecker(db, nil); err == nil {
		t.Fatal("nil metrics must be rejected")
	}
}
