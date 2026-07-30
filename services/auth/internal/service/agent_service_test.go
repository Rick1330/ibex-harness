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

func TestUnit_AgentService_ValidateForOrg(t *testing.T) {
	t.Parallel()

	orgID := uuid.New()
	agentID := uuid.New()
	cases := []struct {
		name    string
		repo    *fakeAgentRepo
		wantErr error
		wantOK  bool
	}{
		{
			name: "ok",
			repo: &fakeAgentRepo{rec: &repository.AgentRecord{
				ID: agentID.String(), OrgID: orgID.String(), Status: "active",
			}},
			wantOK: true,
		},
		{
			name:    "missing",
			repo:    &fakeAgentRepo{},
			wantErr: ErrAgentNotAuthorized,
		},
		{
			name: "inactive",
			repo: &fakeAgentRepo{rec: &repository.AgentRecord{
				ID: agentID.String(), OrgID: orgID.String(), Status: "paused",
			}},
			wantErr: ErrAgentNotAuthorized,
		},
		{
			name:    "store error",
			repo:    &fakeAgentRepo{err: errors.New("db down")},
			wantErr: ErrAgentLookup,
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			svc, err := NewAgentService(tc.repo)
			if err != nil {
				t.Fatalf("NewAgentService: %v", err)
			}
			view, err := svc.ValidateForOrg(context.Background(), orgID, agentID)
			if tc.wantErr != nil {
				if !errors.Is(err, tc.wantErr) {
					t.Fatalf("err=%v want %v", err, tc.wantErr)
				}
				return
			}
			if err != nil {
				t.Fatalf("ValidateForOrg: %v", err)
			}
			if !tc.wantOK {
				t.Fatal("expected ok")
			}
			if view.ID != agentID.String() || view.OrgID != orgID.String() || view.Status != "active" {
				t.Fatalf("view=%+v", view)
			}
		})
	}
}
