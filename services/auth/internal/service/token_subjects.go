package service

import (
	"context"
	"errors"
	"fmt"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
)

// ErrTokenSubjectForbidden indicates agent_id/user_id is missing for the org
// or belongs to another org. Callers must map this to PERMISSION_DENIED.
var ErrTokenSubjectForbidden = errors.New("token subject forbidden")

// ErrTokenSubjectLookup indicates a store failure while verifying bind subjects.
var ErrTokenSubjectLookup = errors.New("token subject lookup failed")

// userByOrgLookup loads a user record scoped to an organization.
type userByOrgLookup interface {
	GetByIDAndOrg(ctx context.Context, userID, orgID uuid.UUID) (*repository.UserRecord, error)
}

// tokenSubjectLookup verifies optional CreateToken agent/user binds stay in-org.
type tokenSubjectLookup interface {
	AgentBelongsToOrg(ctx context.Context, agentID, orgID uuid.UUID) (bool, error)
	UserBelongsToOrg(ctx context.Context, userID, orgID uuid.UUID) (bool, error)
}

type repoTokenSubjects struct {
	agents agentByOrgLookup
	users  userByOrgLookup
}

// NewRepoTokenSubjects builds a subject lookup from agent and user repositories.
func NewRepoTokenSubjects(agents agentByOrgLookup, users userByOrgLookup) tokenSubjectLookup {
	return &repoTokenSubjects{agents: agents, users: users}
}

func (s *repoTokenSubjects) AgentBelongsToOrg(ctx context.Context, agentID, orgID uuid.UUID) (bool, error) {
	rec, err := s.agents.GetByIDAndOrg(ctx, agentID, orgID)
	if err != nil {
		return false, err
	}
	return rec != nil, nil
}

func (s *repoTokenSubjects) UserBelongsToOrg(ctx context.Context, userID, orgID uuid.UUID) (bool, error) {
	rec, err := s.users.GetByIDAndOrg(ctx, userID, orgID)
	if err != nil {
		return false, err
	}
	return rec != nil, nil
}

func (s *TokenService) validateCreateTokenSubjects(ctx context.Context, in CreateTokenInput) error {
	if in.AgentID == nil && in.UserID == nil {
		return nil
	}
	if s.subjects == nil {
		return ErrTokenSubjectForbidden
	}
	orgID, err := uuid.Parse(in.OrgID)
	if err != nil {
		return ErrInvalidArgument
	}
	if err := s.validateOptionalAgentBind(ctx, orgID, in.AgentID); err != nil {
		return err
	}
	return s.validateOptionalUserBind(ctx, orgID, in.UserID)
}

func (s *TokenService) validateOptionalAgentBind(ctx context.Context, orgID uuid.UUID, raw *string) error {
	if raw == nil {
		return nil
	}
	agentID, err := parseOptionalSubjectID(*raw)
	if err != nil {
		return err
	}
	ok, err := s.subjects.AgentBelongsToOrg(ctx, agentID, orgID)
	if err != nil {
		return fmt.Errorf("%w: %w", ErrTokenSubjectLookup, err)
	}
	if !ok {
		return ErrTokenSubjectForbidden
	}
	return nil
}

func (s *TokenService) validateOptionalUserBind(ctx context.Context, orgID uuid.UUID, raw *string) error {
	if raw == nil {
		return nil
	}
	userID, err := parseOptionalSubjectID(*raw)
	if err != nil {
		return err
	}
	ok, err := s.subjects.UserBelongsToOrg(ctx, userID, orgID)
	if err != nil {
		return fmt.Errorf("%w: %w", ErrTokenSubjectLookup, err)
	}
	if !ok {
		return ErrTokenSubjectForbidden
	}
	return nil
}

func parseOptionalSubjectID(raw string) (uuid.UUID, error) {
	if raw == "" {
		return uuid.Nil, ErrInvalidArgument
	}
	id, err := uuid.Parse(raw)
	if err != nil {
		return uuid.Nil, ErrInvalidArgument
	}
	return id, nil
}
