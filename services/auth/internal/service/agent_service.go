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

// ErrAgentNotAuthorized indicates the agent is missing for the org.
// Callers must map this to PERMISSION_DENIED (not NOT_FOUND) for tenancy safety.
var ErrAgentNotAuthorized = errors.New("agent not authorized")

// ErrAgentInactive indicates the agent exists in-org but is not active.
// Callers must map this to PERMISSION_DENIED with an existence-safe client message;
// metrics may still distinguish inactive from missing.
var ErrAgentInactive = errors.New("agent inactive")

// ErrAgentLookup indicates a store failure during agent validation.
var ErrAgentLookup = errors.New("agent lookup failed")

// agentByOrgLookup loads an agent record scoped to an organization.
// Named for the single GetByIDAndOrg method (Go -er interface convention).
type agentByOrgLookup interface {
	GetByIDAndOrg(ctx context.Context, agentID, orgID uuid.UUID) (*repository.AgentRecord, error)
}

// AgentService validates agent identity for an organization.
type AgentService struct {
	repo agentByOrgLookup
}

// NewAgentService constructs an AgentService.
// It rejects a nil lookup dependency so wiring fails fast at construction
// instead of deferring a nil panic to the first ValidateForOrg call.
func NewAgentService(repo agentByOrgLookup) (*AgentService, error) {
	if repo == nil {
		return nil, fmt.Errorf("service: nil agent repo")
	}
	return &AgentService{repo: repo}, nil
}

// ValidateForOrg returns the agent when it exists in orgID and is active.
func (s *AgentService) ValidateForOrg(ctx context.Context, orgID, agentID uuid.UUID) (AgentView, error) {
	rec, err := s.repo.GetByIDAndOrg(ctx, agentID, orgID)
	if err != nil {
		return AgentView{}, fmt.Errorf("%w: %w", ErrAgentLookup, err)
	}
	if rec == nil {
		return AgentView{}, ErrAgentNotAuthorized
	}
	if rec.Status != "active" {
		return AgentView{}, ErrAgentInactive
	}
	return AgentView{ID: rec.ID, OrgID: rec.OrgID, Status: rec.Status}, nil
}
