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
	notify chan struct{}
}

func newRecordingPublisher(err error) *recordingPublisher {
	return &recordingPublisher{err: err, notify: make(chan struct{}, 8)}
}

func (p *recordingPublisher) Publish(_ context.Context, event revocation.RevocationEvent) error {
	p.mu.Lock()
	p.events = append(p.events, event)
	p.mu.Unlock()
	select {
	case p.notify <- struct{}{}:
	default:
	}
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

type revokeFixture struct {
	orgID   string
	tokenID string
	repo    *memTokenRepo
	pub     *recordingPublisher
	svc     *TokenService
}

func newRevokeFixture(t *testing.T, pubErr error) revokeFixture {
	t.Helper()
	orgID := uuid.New().String()
	tokenID := uuid.New().String()
	repo := newMemTokenRepo()
	repo.tokens[tokenID] = repository.CreateTokenParams{ID: tokenID, OrgID: orgID}
	pub := newRecordingPublisher(pubErr)
	svc := NewTokenService(repo, token.DefaultArgon2Params(), logger.Discard("auth"), pub)
	return revokeFixture{orgID: orgID, tokenID: tokenID, repo: repo, pub: pub, svc: svc}
}

func TestUnit_RevokeTokenPublishesEvent(t *testing.T) {
	t.Parallel()
	f := revokeAndAwaitPublish(t, nil)
	assertRevokeEvent(t, f.pub.last(), f.tokenID, f.orgID)
}

func TestUnit_RevokeTokenPublishFailureDoesNotFailRevoke(t *testing.T) {
	t.Parallel()
	f := revokeAndAwaitPublish(t, context.DeadlineExceeded)
	if !f.repo.revoked[f.tokenID] {
		t.Fatal("token not revoked")
	}
}

func TestUnit_DrainPublishesCancelsInFlight(t *testing.T) {
	t.Parallel()
	f := newRevokeFixture(t, nil)
	mustRevokeToken(t, f)
	f.svc.DrainPublishes()
	if f.pub.count() < 1 {
		t.Fatal("expected publish before drain completed")
	}
}

func revokeAndAwaitPublish(t *testing.T, pubErr error) revokeFixture {
	t.Helper()
	f := newRevokeFixture(t, pubErr)
	mustRevokeToken(t, f)
	waitPublish(t, f.pub, 1)
	f.svc.WaitPendingPublishes()
	return f
}

func mustRevokeToken(t *testing.T, f revokeFixture) {
	t.Helper()
	err := f.svc.RevokeToken(context.Background(), RevokeTokenParams{
		OrgID: f.orgID, TokenID: f.tokenID,
	})
	if err != nil {
		t.Fatalf("RevokeToken: %v", err)
	}
}

func assertRevokeEvent(t *testing.T, got revocation.RevocationEvent, tokenID, orgID string) {
	t.Helper()
	assertFieldEQ(t, "token_id", got.TokenID, tokenID)
	assertFieldEQ(t, "org_id", got.OrgID, orgID)
	assertVersionEQ(t, got.Version, 1)
}

func assertFieldEQ(t *testing.T, name, got, want string) {
	t.Helper()
	if got != want {
		t.Fatalf("%s=%q want %q", name, got, want)
	}
}

func assertVersionEQ(t *testing.T, got, want int) {
	t.Helper()
	if got != want {
		t.Fatalf("version=%d want %d", got, want)
	}
}

func waitPublish(t *testing.T, pub *recordingPublisher, want int) {
	t.Helper()
	deadline := time.After(time.Second)
	for pub.count() < want {
		select {
		case <-pub.notify:
		case <-deadline:
			t.Fatalf("publish count=%d want %d", pub.count(), want)
		}
	}
}
