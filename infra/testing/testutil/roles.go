//go:build integration

package testutil

import (
	"context"
	"database/sql"

	"github.com/Rick1330/ibex-harness/infra/testing/runtimeconn"
)

// ResetCapabilityRoles delegates to the proto-free leaf package so callers that
// cannot import this package (it pulls generated protobuf) can still reset the
// capability logins.
func ResetCapabilityRoles(ctx context.Context, db *sql.DB) {
	runtimeconn.ResetCapabilityRoles(ctx, db)
}
