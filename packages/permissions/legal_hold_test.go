package permissions_test

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
)

func TestLegalHoldManage_StepUpAndAdminDefault(t *testing.T) {
	t.Parallel()
	if permissions.LegalHoldManage != 1<<49 {
		t.Fatalf("bit=%d", permissions.LegalHoldManage)
	}
	if !permissions.RequiresStepUp(permissions.LegalHoldManage) {
		t.Fatal("expected step-up")
	}
	adminOps := permissions.AdminOperatorDefault
	if !permissions.Has(adminOps, permissions.LegalHoldManage) {
		t.Fatal("AdminOperatorDefault must include LegalHoldManage")
	}
}
