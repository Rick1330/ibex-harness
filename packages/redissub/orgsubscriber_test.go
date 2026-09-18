package redissub_test

import (
	"context"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/redissub"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func TestUnit_NewOrgSubscriber_validation(t *testing.T) {
	t.Parallel()
	log := logger.Discard("redissub-sub")
	client := redis.NewClient(&redis.Options{Addr: "127.0.0.1:0"})
	t.Cleanup(func() { _ = client.Close() })
	cache := &recordingInvalidator{seen: make(chan uuid.UUID, 1)}
	parse := func(string) (string, error) { return "", nil }

	tests := []struct {
		name    string
		cfg     redissub.OrgSubscriberConfig
		wantErr string
	}{
		{
			name: "nil client",
			cfg: redissub.OrgSubscriberConfig{
				Cache: cache, Log: log, Parse: parse, ErrPrefix: "mydomain",
			},
			wantErr: "mydomain: redis client is required",
		},
		{
			name: "nil cache",
			cfg: redissub.OrgSubscriberConfig{
				Client: client, Log: log, Parse: parse, ErrPrefix: "mydomain",
			},
			wantErr: "mydomain: cache is required",
		},
		{
			name: "nil log",
			cfg: redissub.OrgSubscriberConfig{
				Client: client, Cache: cache, Parse: parse, ErrPrefix: "mydomain",
			},
			wantErr: "mydomain: logger is required",
		},
		{
			name: "nil parse",
			cfg: redissub.OrgSubscriberConfig{
				Client: client, Cache: cache, Log: log, ErrPrefix: "mydomain",
			},
			wantErr: "mydomain: parse is required",
		},
		{
			name: "nil client default prefix",
			cfg: redissub.OrgSubscriberConfig{
				Cache: cache, Log: log, Parse: parse,
			},
			wantErr: "redissub: redis client is required",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			_, err := redissub.NewOrgSubscriber(tt.cfg)
			if err == nil {
				t.Fatal("expected error")
			}
			if !strings.Contains(err.Error(), tt.wantErr) {
				t.Fatalf("err=%q want substring %q", err.Error(), tt.wantErr)
			}
		})
	}
}

func TestUnit_OrgSubscriber_goodPayloadInvalidates(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	rec := &recordingInvalidator{seen: make(chan uuid.UUID, 4)}
	client := newMiniRedis(t)
	startOrgSubscriber(t, client, rec, parseOrgID)

	waitPubSubPatterns(t, client)
	mustPublish(t, client, "ibex:test:invalidate:"+org.String(),
		`{"v":1,"org_id":"`+org.String()+`","epoch":1}`)
	waitInvalidated(t, rec, org)
}

func TestUnit_OrgSubscriber_malformedIgnored(t *testing.T) {
	t.Parallel()
	runIgnoreThenSentinel(t, ignoreThenSentinelCase{
		badChannelOrg: uuid.New(),
		badPayload:    `{`,
	})
}

func TestUnit_OrgSubscriber_orgMismatchIgnored(t *testing.T) {
	t.Parallel()
	channelOrg := uuid.New()
	runIgnoreThenSentinel(t, ignoreThenSentinelCase{
		badChannelOrg: channelOrg,
		badPayload:    `{"v":1,"org_id":"` + uuid.New().String() + `","epoch":1}`,
	})
}

type ignoreThenSentinelCase struct {
	badChannelOrg uuid.UUID
	badPayload    string
}

func runIgnoreThenSentinel(t *testing.T, tc ignoreThenSentinelCase) {
	t.Helper()
	rec := &recordingInvalidator{seen: make(chan uuid.UUID, 4)}
	client := newMiniRedis(t)
	startOrgSubscriber(t, client, rec, parseOrgID)
	waitPubSubPatterns(t, client)

	prefix := "ibex:test:invalidate:"
	mustPublish(t, client, prefix+tc.badChannelOrg.String(), tc.badPayload)

	sentinel := uuid.New()
	mustPublish(t, client, prefix+sentinel.String(),
		`{"v":1,"org_id":"`+sentinel.String()+`","epoch":1}`)
	waitInvalidated(t, rec, sentinel)

	if got := rec.orgsSnapshot(); len(got) != 1 || got[0] != sentinel {
		t.Fatalf("invalidated=%v want only sentinel %s", got, sentinel)
	}
}

func TestUnit_OrgSubscriber_StopUnblocksRun(t *testing.T) {
	t.Parallel()
	client := newMiniRedis(t)
	rec := &recordingInvalidator{seen: make(chan uuid.UUID, 1)}
	sub, err := redissub.NewOrgSubscriber(redissub.OrgSubscriberConfig{
		Client:        client,
		Cache:         rec,
		Log:           logger.Discard("redissub-stop"),
		ChannelPrefix: "ibex:test:invalidate:",
		Parse:         parseOrgID,
	})
	if err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{})
	go func() {
		sub.Run(context.Background(), "test-sub")
		close(done)
	}()
	waitPubSubPatterns(t, client)
	sub.Stop()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("Stop did not unblock Run within 2s")
	}
}

type recordingInvalidator struct {
	seen chan uuid.UUID
	mu   sync.Mutex
	orgs []uuid.UUID
}

func (r *recordingInvalidator) Invalidate(orgID uuid.UUID) {
	r.mu.Lock()
	r.orgs = append(r.orgs, orgID)
	r.mu.Unlock()
	select {
	case r.seen <- orgID:
	default:
	}
}

func (r *recordingInvalidator) orgsSnapshot() []uuid.UUID {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make([]uuid.UUID, len(r.orgs))
	copy(out, r.orgs)
	return out
}

func parseOrgID(payload string) (string, error) {
	ev, err := redissub.ParseOrgEvent(payload, redissub.EventPolicy{
		ErrPrefix:      "testdomain",
		CurrentVersion: 1,
		RequireEpoch:   true,
	})
	if err != nil {
		return "", err
	}
	return ev.OrgID, nil
}

func newMiniRedis(t *testing.T) *redis.Client {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return client
}

func startOrgSubscriber(t *testing.T, client redis.UniversalClient, cache redissub.OrgInvalidator, parse func(string) (string, error)) {
	t.Helper()
	sub, err := redissub.NewOrgSubscriber(redissub.OrgSubscriberConfig{
		Client:        client,
		Cache:         cache,
		Log:           logger.Discard("redissub-test"),
		ChannelPrefix: "ibex:test:invalidate:",
		Parse:         parse,
	})
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	go sub.Run(ctx, "test-sub")
	t.Cleanup(func() {
		sub.Stop()
		<-sub.Done()
	})
}

func mustPublish(t *testing.T, client redis.UniversalClient, channel, payload string) {
	t.Helper()
	if err := client.Publish(context.Background(), channel, payload).Err(); err != nil {
		t.Fatal(err)
	}
}

func waitInvalidated(t *testing.T, rec *recordingInvalidator, want uuid.UUID) {
	t.Helper()
	deadline := time.After(2 * time.Second)
	for {
		select {
		case got := <-rec.seen:
			if got == want {
				return
			}
		case <-deadline:
			t.Fatalf("timed out waiting for invalidate of %s; saw %v", want, rec.orgsSnapshot())
		}
	}
}

func waitPubSubPatterns(t *testing.T, client redis.UniversalClient) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		n, err := client.PubSubNumPat(context.Background()).Result()
		if err == nil && n > 0 {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatal("pubsub pattern not registered within 2s")
}
