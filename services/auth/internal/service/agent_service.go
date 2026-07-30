package service

import (
	"context"
	"errors"
	"fmt"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
)

// AgentView is the service-layer projection of an authorized agent.
type AgentView struct {
	ID     string
	OrgID  string
	Status string
}

// ErrAgentNotAuthorized indicates the agent is missing for the org or inactive.
// Callers must map this to PERMISSION_DENIED (not NOT_FOUND) for tenancy safety.
var ErrAgentNotAuthorized = errors.New("agent not authorized")

// ErrAgentLookup indicates a store failure during agent validation.
var ErrAgentLookup = errors.New("agent lookup failed")

type agentRepo interface {
	GetByIDAndOrg(ctx context.Context, agentID, orgID uuid.UUID) (*repository.AgentRecord, error)
}

// AgentService validates agent identity for an organization.
type AgentService struct {
	repo agentRepo
}

// NewAgentService constructs an AgentService.
func NewAgentService(repo agentRepo) (*AgentService, error) {
	if repo == nil {
		return nil, fmt.Errorf("service: nil agent repo")
	}
	return &AgentService{repo: repo}, nil
}

// ValidateForOrg returns the agent when it exists in orgID and is active.
func (s *AgentService) ValidateForOrg(ctx context.Context, orgID, agentID uuid.UUID) (AgentView, error) {
	rec, err := s.repo.GetByIDAndOrg(ctx, agentID, orgID)
	if err != nil {
		return AgentView{}, fmt.Errorf("%w: %v", ErrAgentLookup, err)
	}
	if rec == nil || rec.Status != "active" {
		return AgentView{}, ErrAgentNotAuthorized
	}
	return AgentView{ID: rec.ID, OrgID: rec.OrgID, Status: rec.Status}, nil
}
