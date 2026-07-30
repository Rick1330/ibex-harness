package service

import (
	"context"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
)

type fakeAgentRepo struct {
	rec *repository.AgentRecord
	err error
}

func (f *fakeAgentRepo) GetByIDAndOrg(context.Context, uuid.UUID, uuid.UUID) (*repository.AgentRecord, error) {
	return f.rec, f.err
}

func TestUnit_NewAgentService_RejectsNilRepo(t *testing.T) {
	t.Parallel()
	if _, err := NewAgentService(nil); err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_AgentService_ValidateForOrg_OK(t *testing.T) {
	t.Parallel()
	orgID, agentID := uuid.New(), uuid.New()
	view, err := mustValidateForOrg(t, &fakeAgentRepo{rec: &repository.AgentRecord{
		ID: agentID.String(), OrgID: orgID.String(), Status: "active",
	}}, orgID, agentID)
	if err != nil {
		t.Fatalf("ValidateForOrg: %v", err)
	}
	assertActiveAgentView(t, view, agentID, orgID)
}

func assertActiveAgentView(t *testing.T, view AgentView, agentID, orgID uuid.UUID) {
	t.Helper()
	if view.ID != agentID.String() {
		t.Fatalf("id=%q want %s", view.ID, agentID)
	}
	if view.OrgID != orgID.String() {
		t.Fatalf("org_id=%q want %s", view.OrgID, orgID)
	}
	if view.Status != "active" {
		t.Fatalf("status=%q want active", view.Status)
	}
}

func TestUnit_AgentService_ValidateForOrg_Missing(t *testing.T) {
	t.Parallel()
	assertValidateForOrgErr(t, &fakeAgentRepo{}, ErrAgentNotAuthorized)
}

func TestUnit_AgentService_ValidateForOrg_Inactive(t *testing.T) {
	t.Parallel()
	orgID, agentID := uuid.New(), uuid.New()
	repo := &fakeAgentRepo{rec: &repository.AgentRecord{
		ID: agentID.String(), OrgID: orgID.String(), Status: "paused",
	}}
	_, err := mustValidateForOrg(t, repo, orgID, agentID)
	if !errors.Is(err, ErrAgentInactive) {
		t.Fatalf("err=%v want %v", err, ErrAgentInactive)
	}
}

func TestUnit_AgentService_ValidateForOrg_StoreError(t *testing.T) {
	t.Parallel()
	assertValidateForOrgErr(t, &fakeAgentRepo{err: errors.New("db down")}, ErrAgentLookup)
}

func TestUnit_AgentService_ValidateForOrg_UnwrapsCause(t *testing.T) {
	t.Parallel()
	cause := context.Canceled
	_, err := mustValidateForOrg(t, &fakeAgentRepo{err: cause}, uuid.New(), uuid.New())
	if !errors.Is(err, ErrAgentLookup) {
		t.Fatalf("err=%v want ErrAgentLookup", err)
	}
	if !errors.Is(err, cause) {
		t.Fatalf("err=%v want unwrap %v", err, cause)
	}
}

func mustValidateForOrg(t *testing.T, repo *fakeAgentRepo, orgID, agentID uuid.UUID) (AgentView, error) {
	t.Helper()
	svc, err := NewAgentService(repo)
	if err != nil {
		t.Fatalf("NewAgentService: %v", err)
	}
	return svc.ValidateForOrg(context.Background(), orgID, agentID)
}

func assertValidateForOrgErr(t *testing.T, repo *fakeAgentRepo, want error) {
	t.Helper()
	_, err := mustValidateForOrg(t, repo, uuid.New(), uuid.New())
	if !errors.Is(err, want) {
		t.Fatalf("err=%v want %v", err, want)
	}
}
