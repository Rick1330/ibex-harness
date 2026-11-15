//go:build integration

package pgtenant_test

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/runtimeconn"
	"github.com/Rick1330/ibex-harness/packages/pgtenant"
	"github.com/google/uuid"
)

// These two benchmarks price the pin: the same BEGIN/preamble/COMMIT with and
// without SET LOCAL ROLE, so the delta is exactly one extra round trip. Run
// against the compose test database:
//
//	go test -tags=integration -run '^$' -bench BenchmarkPreamble -benchtime 3000x -count 10 ./packages/pgtenant/
//
// On loopback the preamble costs ~334us and the pin adds ~72us (median of 10,
// stdev ~20us). The absolute numbers are loopback, not production; the delta
// scales with the database round-trip time, because it is one round trip.
func BenchmarkPreambleGUCOnly(b *testing.B) { benchPreamble(b, false) }

func BenchmarkPreamblePinned(b *testing.B) { benchPreamble(b, true) }

func benchPreamble(b *testing.B, pin bool) {
	b.Helper()
	db := runtimeconn.OpenDB(b, runtimeconn.DSN())
	defer func() { _ = db.Close() }()
	ctx := context.Background()
	org := uuid.New()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		tx, err := db.BeginTx(ctx, nil)
		if err != nil {
			b.Fatal(err)
		}
		if pin {
			err = pgtenant.PinOrg(ctx, tx, org)
		} else {
			_, err = tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, org.String())
		}
		if err != nil {
			b.Fatal(err)
		}
		if err := tx.Commit(); err != nil {
			b.Fatal(err)
		}
	}
}
