package bootstrap

import (
	"context"
	"errors"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/google/uuid"
)

func TestPinRelayRole_URLPreservesParamsAndPinsRole(t *testing.T) {
	pinned, err := pinRelayRole("postgres://relay:pw@db:5432/ibex?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	u, err := url.Parse(pinned)
	if err != nil {
		t.Fatal(err)
	}
	if got := u.Query().Get("options"); got != "-c role=ibex_evidence_relay" {
		t.Fatalf("options: got %q", got)
	}
	if got := u.Query().Get("sslmode"); got != "disable" {
		t.Fatalf("sslmode lost: %q", got)
	}
	if u.User.String() != "relay:pw" || u.Path != "/ibex" {
		t.Fatalf("dsn rewritten unexpectedly: %s", pinned)
	}
}

func TestPinRelayRole_URLAppendsExistingOptions(t *testing.T) {
	pinned, err := pinRelayRole("postgres://relay:pw@db:5432/ibex?options=-c%20statement_timeout%3D5000")
	if err != nil {
		t.Fatal(err)
	}
	u, err := url.Parse(pinned)
	if err != nil {
		t.Fatal(err)
	}
	got := u.Query().Get("options")
	if !strings.Contains(got, "statement_timeout=5000") || !strings.Contains(got, "-c role=ibex_evidence_relay") {
		t.Fatalf("options merge: got %q", got)
	}
}

func TestPinRelayRole_KeywordForm(t *testing.T) {
	pinned, err := pinRelayRole("host=db port=5432 user=relay password=pw dbname=ibex sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasSuffix(pinned, " options='-c role=ibex_evidence_relay'") {
		t.Fatalf("keyword pin: %s", pinned)
	}
}

func TestPinRelayRole_Rejections(t *testing.T) {
	if _, err := pinRelayRole("   "); err == nil {
		t.Fatal("empty dsn must be rejected")
	}
	if _, err := pinRelayRole("host=db options='-c statement_timeout=5000'"); err == nil {
		t.Fatal("keyword form with existing options must be rejected")
	}
}

func TestPinRelayRole_InvalidURLDoesNotLeakCredentials(t *testing.T) {
	_, err := pinRelayRole("postgres://relay:supersecret@%zz/db")
	if err == nil {
		t.Fatal("invalid dsn must be rejected")
	}
	if strings.Contains(err.Error(), "supersecret") || strings.Contains(err.Error(), "%zz") {
		t.Fatalf("error leaks dsn material: %v", err)
	}
}

func TestAssertRelayRole(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })

	mock.ExpectQuery("SELECT current_user").
		WillReturnRows(sqlmock.NewRows([]string{"current_user"}).AddRow("ibex_evidence_relay"))
	if err := assertRelayRole(context.Background(), db); err != nil {
		t.Fatalf("relay role must pass: %v", err)
	}

	mock.ExpectQuery("SELECT current_user").
		WillReturnRows(sqlmock.NewRows([]string{"current_user"}).AddRow("ibex_app"))
	err = assertRelayRole(context.Background(), db)
	if err == nil || !strings.Contains(err.Error(), "ibex_evidence_relay") {
		t.Fatalf("unexpected role must fail closed, got %v", err)
	}
}

type fakeFencedDeliverer struct {
	calls int
	err   error
	fence evidenceoutbox.TombstoneFence
}

func (f *fakeFencedDeliverer) DeliverWithTombstoneFence(_ context.Context, _ evidenceoutbox.OutboxRow, fence evidenceoutbox.TombstoneFence) error {
	f.calls++
	f.fence = fence
	return f.err
}

func TestMetricsDeliverer_RecordsSuccessAndFailure(t *testing.T) {
	reg := ibexmetrics.NewRelay("test-relay")
	inner := &fakeFencedDeliverer{}
	d := newMetricsDeliverer(inner, reg, 0)
	row := evidenceoutbox.OutboxRow{OrgID: uuid.New()}
	fence := evidenceoutbox.TombstoneFence{ResourceType: "session", ResourceID: uuid.New().String(), ResourceVersion: 1}

	if err := d.DeliverWithTombstoneFence(context.Background(), row, fence); err != nil {
		t.Fatalf("delivery: %v", err)
	}
	inner.err = errors.New("sink down")
	if err := d.DeliverWithTombstoneFence(context.Background(), row, fence); err == nil {
		t.Fatal("expected delivery error")
	}
	if inner.calls != 2 || inner.fence != fence {
		t.Fatalf("inner calls=%d fence=%+v", inner.calls, inner.fence)
	}
	if got := metricSeriesCount(t, reg, "ibex_relay_delivery_duration_seconds"); got != 2 {
		t.Fatalf("delivery duration series: got %d want 2", got)
	}
}

func TestMetricsDeliverer_BoundsDeliveryDeadline(t *testing.T) {
	reg := ibexmetrics.NewRelay("test-relay")
	d := newMetricsDeliverer(blockingFencedDeliverer{}, reg, 40*time.Millisecond)
	fence := evidenceoutbox.TombstoneFence{ResourceType: "session", ResourceID: uuid.New().String(), ResourceVersion: 1}
	err := d.DeliverWithTombstoneFence(context.Background(), evidenceoutbox.OutboxRow{OrgID: uuid.New()}, fence)
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("want deadline exceeded, got %v", err)
	}
}

func TestDeliveryDeadlineFor_ReservesPersistenceBudget(t *testing.T) {
	cases := []struct {
		op   time.Duration
		want time.Duration
	}{
		{0, 0},
		{time.Second, 500 * time.Millisecond},
		{10 * time.Second, 7500 * time.Millisecond},
		{time.Minute, 55 * time.Second},
	}
	for _, tc := range cases {
		if got := deliveryDeadlineFor(tc.op); got != tc.want {
			t.Fatalf("deliveryDeadlineFor(%s) = %s, want %s", tc.op, got, tc.want)
		}
		if tc.op > 0 && deliveryDeadlineFor(tc.op) >= tc.op {
			t.Fatalf("delivery deadline for %s must leave a reserve", tc.op)
		}
	}
}

type blockingFencedDeliverer struct{}

func (blockingFencedDeliverer) DeliverWithTombstoneFence(ctx context.Context, _ evidenceoutbox.OutboxRow, _ evidenceoutbox.TombstoneFence) error {
	<-ctx.Done()
	return ctx.Err()
}

func TestMetricsDeliverer_LegacyDeliverFailsClosedWithoutFence(t *testing.T) {
	reg := ibexmetrics.NewRelay("test-relay")
	d := newMetricsDeliverer(&fakeFencedDeliverer{}, reg, 0)
	if err := d.Deliver(context.Background(), evidenceoutbox.OutboxRow{}); err == nil {
		t.Fatal("fence-less delivery must fail closed")
	}
	row := evidenceoutbox.OutboxRow{TombstoneFence: &evidenceoutbox.TombstoneFence{
		ResourceType: "session", ResourceID: uuid.New().String(), ResourceVersion: 1,
	}}
	if err := d.Deliver(context.Background(), row); err != nil {
		t.Fatalf("fenced legacy delivery: %v", err)
	}
}

func TestCloseRuntime_NilAndEmptyRuntimeAreNoops(t *testing.T) {
	if err := closeRuntime(nil); err != nil {
		t.Fatalf("closeRuntime(nil): %v", err)
	}
	if err := closeSink(nil); err != nil {
		t.Fatalf("closeSink(nil): %v", err)
	}
	if err := closeDB(nil); err != nil {
		t.Fatalf("closeDB(nil): %v", err)
	}
}

func TestOpenRelayDB_EmptyDSNFailsClosed(t *testing.T) {
	if _, err := openRelayDB(context.Background(), "   ", time.Second); err == nil {
		t.Fatal("empty DSN must fail closed")
	}
}

func TestAssertRelayRole_QueryErrorIsWrapped(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	mock.ExpectQuery("SELECT current_user").WillReturnError(errors.New("connection reset"))
	if err := assertRelayRole(context.Background(), db); err == nil {
		t.Fatal("query failure must surface")
	}
}
