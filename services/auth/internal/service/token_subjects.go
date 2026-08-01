package service

import (
	"context"
	"errors"
	"fmt"
	"reflect"

	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
)

// ErrTokenSubjectForbidden indicates agent_id/user_id is missing for the org
// or belongs to another org. Callers must map this to PERMISSION_DENIED.
var ErrTokenSubjectForbidden = errors.New("token subject forbidden")

// ErrTokenSubjectLookup indicates a store failure while verifying bind subjects.
var ErrTokenSubjectLookup = errors.New("token subject lookup failed")

// ErrTokenSubjectUnavailable indicates subject lookup was not wired (misconfig).
// Callers must map this to Internal and must not treat it as a tenant denial.
var ErrTokenSubjectUnavailable = errors.New("token subject lookup unavailable")

// userOrgFinder loads a user record scoped to an organization.
type userOrgFinder interface {
	Find(ctx context.Context, userID, orgID uuid.UUID) (*repository.UserRecord, error)
}

// tokenSubjectLookup verifies optional CreateToken agent/user binds stay in-org.
type tokenSubjectLookup interface {
	AgentBelongsToOrg(ctx context.Context, agentID, orgID uuid.UUID) (bool, error)
	UserBelongsToOrg(ctx context.Context, userID, orgID uuid.UUID) (bool, error)
}

type subjectBelongsFn func(ctx context.Context, id, orgID uuid.UUID) (bool, error)

type repoTokenSubjects struct {
	agents agentByOrgLookup
	users  userOrgFinder
}

type usersFindAdapter struct {
	repo *repository.UsersRepository
}

// UsersFinder adapts UsersRepository to userOrgFinder for NewRepoTokenSubjects.
func UsersFinder(repo *repository.UsersRepository) userOrgFinder {
	if repo == nil {
		return nil
	}
	return usersFindAdapter{repo: repo}
}

func (a usersFindAdapter) Find(ctx context.Context, userID, orgID uuid.UUID) (*repository.UserRecord, error) {
	return a.repo.GetByIDAndOrg(ctx, userID, orgID)
}

// NewRepoTokenSubjects builds a subject lookup from agent and user repositories.
func NewRepoTokenSubjects(agents agentByOrgLookup, users userOrgFinder) (tokenSubjectLookup, error) {
	if isNilSubjectDep(agents) {
		return nil, fmt.Errorf("service: nil agent subject lookup")
	}
	if isNilSubjectDep(users) {
		return nil, fmt.Errorf("service: nil user subject lookup")
	}
	return &repoTokenSubjects{agents: agents, users: users}, nil
}

func isNilSubjectDep(v any) bool {
	if v == nil {
		return true
	}
	rv := reflect.ValueOf(v)
	switch rv.Kind() {
	case reflect.Chan, reflect.Func, reflect.Interface, reflect.Map, reflect.Ptr, reflect.Slice:
		return rv.IsNil()
	default:
		return false
	}
}

func (s *repoTokenSubjects) AgentBelongsToOrg(ctx context.Context, agentID, orgID uuid.UUID) (bool, error) {
	rec, err := s.agents.GetByIDAndOrg(ctx, agentID, orgID)
	if err != nil {
		return false, err
	}
	return rec != nil, nil
}

func (s *repoTokenSubjects) UserBelongsToOrg(ctx context.Context, userID, orgID uuid.UUID) (bool, error) {
	rec, err := s.users.Find(ctx, userID, orgID)
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
		return ErrTokenSubjectUnavailable
	}
	orgID, err := uuid.Parse(in.OrgID)
	if err != nil {
		return ErrInvalidArgument
	}
	if err := s.validateOptionalSubjectBind(ctx, orgID, in.AgentID, s.subjects.AgentBelongsToOrg); err != nil {
		return err
	}
	return s.validateOptionalSubjectBind(ctx, orgID, in.UserID, s.subjects.UserBelongsToOrg)
}

func (s *TokenService) validateOptionalSubjectBind(
	ctx context.Context,
	orgID uuid.UUID,
	raw *string,
	belongs subjectBelongsFn,
) error {
	if raw == nil {
		return nil
	}
	id, err := parseOptionalSubjectID(*raw)
	if err != nil {
		return err
	}
	ok, err := belongs(ctx, id, orgID)
	if err != nil {
		return fmt.Errorf("%w org_id=%s subject_id=%s: %w", ErrTokenSubjectLookup, orgID, id, err)
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

// TokenBindResourceID formats optional bind subjects for internal audit logs.
func TokenBindResourceID(in CreateTokenInput) string {
	switch {
	case in.AgentID != nil && in.UserID != nil:
		return "agent:" + *in.AgentID + ",user:" + *in.UserID
	case in.AgentID != nil:
		return *in.AgentID
	case in.UserID != nil:
		return *in.UserID
	default:
		return ""
	}
}
