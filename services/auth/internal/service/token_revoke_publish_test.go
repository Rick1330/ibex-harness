package service

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
)

type recordingPublisher struct {
	mu     sync.Mutex
	events []revocation.RevocationEvent
	err    error
}

func (p *recordingPublisher) Publish(_ context.Context, event revocation.RevocationEvent) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.events = append(p.events, event)
	return p.err
}

func (p *recordingPublisher) count() int {
	p.mu.Lock()
	defer p.mu.Unlock()
	return len(p.events)
}

func (p *recordingPublisher) last() revocation.RevocationEvent {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.events[len(p.events)-1]
}

func TestUnit_RevokeTokenPublishesEvent(t *testing.T) {
	t.Parallel()
	orgID := uuid.New().String()
	tokenID := uuid.New().String()
	repo := newMemTokenRepo()
	repo.tokens[tokenID] = repository.CreateTokenParams{ID: tokenID, OrgID: orgID}
	pub := &recordingPublisher{}
	svc := NewTokenService(repo, token.DefaultArgon2Params(), logger.Discard("auth"), pub)

	if err := svc.RevokeToken(context.Background(), orgID, tokenID, "", nil); err != nil {
		t.Fatalf("RevokeToken: %v", err)
	}
	waitPublish(t, pub, 1)
	svc.WaitPendingPublishes()
	assertRevokeEvent(t, pub.last(), tokenID, orgID)
}

func assertRevokeEvent(t *testing.T, got revocation.RevocationEvent, tokenID, orgID string) {
	t.Helper()
	if got.TokenID != tokenID {
		t.Fatalf("token_id=%q want %q", got.TokenID, tokenID)
	}
	if got.OrgID != orgID {
		t.Fatalf("org_id=%q want %q", got.OrgID, orgID)
	}
	if got.Version != 1 {
		t.Fatalf("version=%d want 1", got.Version)
	}
}

func TestUnit_RevokeTokenPublishFailureDoesNotFailRevoke(t *testing.T) {
	t.Parallel()
	orgID := uuid.New().String()
	tokenID := uuid.New().String()
	repo := newMemTokenRepo()
	repo.tokens[tokenID] = repository.CreateTokenParams{ID: tokenID, OrgID: orgID}
	pub := &recordingPublisher{err: context.DeadlineExceeded}
	svc := NewTokenService(repo, token.DefaultArgon2Params(), logger.Discard("auth"), pub)

	if err := svc.RevokeToken(context.Background(), orgID, tokenID, "", nil); err != nil {
		t.Fatalf("RevokeToken must succeed: %v", err)
	}
	if !repo.revoked[tokenID] {
		t.Fatal("token not revoked")
	}
	waitPublish(t, pub, 1)
	svc.WaitPendingPublishes()
}

func waitPublish(t *testing.T, pub *recordingPublisher, want int) {
	t.Helper()
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		if pub.count() >= want {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	t.Fatalf("publish count=%d want %d", pub.count(), want)
}
