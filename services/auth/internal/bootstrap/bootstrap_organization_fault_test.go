package bootstrap

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

// These tests prove `insertOrganization` on its own: the three answers the
// upsert can give (fresh insert, existing organization, soft-deleted
// organization) and the read failure that must be propagated.

// runInsertOrganization drives insertOrganization once against f, so each
// subtest only states its fault and its assertion.
func runInsertOrganization(t *testing.T, f faultConfig) (bootstrapResult, error) {
	t.Helper()
	db := openFaultDB(t, f)
	in := orgInput{id: uuid.New(), cfg: testConfig(t)}
	return insertOrganization(context.Background(), beginFaultTx(t, db), in)
}

// requireInsertOrganizationError requires insertOrganization to fail with an
// error naming want.
func requireInsertOrganizationError(t *testing.T, f faultConfig, want string) {
	t.Helper()
	_, err := runInsertOrganization(t, f)
	if err == nil || !strings.Contains(err.Error(), want) {
		t.Fatalf("insertOrganization error = %v, want it to name %q", err, want)
	}
}

// mustInsertOrganization requires insertOrganization to succeed and returns its
// result.
func mustInsertOrganization(t *testing.T, f faultConfig) bootstrapResult {
	t.Helper()
	result, err := runInsertOrganization(t, f)
	if err != nil {
		t.Fatalf("insertOrganization: %v", err)
	}
	return result
}

func TestOrganizationHelperErrors(t *testing.T) {
	t.Run("read fails", func(t *testing.T) {
		requireInsertOrganizationError(t, faultConfig{query: errInjected}, "insert organization")
	})

	t.Run("fresh insert", func(t *testing.T) {
		result := mustInsertOrganization(t, faultConfig{rows: []faultRow{organizationRow(true, nil)}})
		if result.AlreadyBootstrapped {
			t.Fatal("insertOrganization reported an existing organization for a fresh insert")
		}
	})

	t.Run("existing organization", func(t *testing.T) {
		existing := uuid.New()
		row := organizationRowFor(false, existing, nil)
		result := mustInsertOrganization(t, faultConfig{rows: []faultRow{row}})
		if !result.AlreadyBootstrapped || result.OrgID != existing {
			t.Fatalf("result = %+v, want already bootstrapped as %s", result, existing)
		}
	})

	t.Run("soft-deleted organization", func(t *testing.T) {
		row := organizationRowFor(false, uuid.New(), time.Now().UTC())
		requireInsertOrganizationError(t, faultConfig{rows: []faultRow{row}}, "soft-deleted")
	})
}
