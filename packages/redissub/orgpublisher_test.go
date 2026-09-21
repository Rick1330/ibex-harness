package redissub_test

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/redissub"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func TestUnit_NewOrgPublisher_validation(t *testing.T) {
	t.Parallel()
	log := logger.Discard("redissub-pub")
	client := redis.NewClient(&redis.Options{Addr: "127.0.0.1:0"})
	t.Cleanup(func() { _ = client.Close() })

	tests := []struct {
		name    string
		cfg     redissub.OrgPublisherConfig
		wantErr string
	}{
		{
			name:    "nil client",
			cfg:     redissub.OrgPublisherConfig{Log: log, ErrPrefix: "mydomain"},
			wantErr: "mydomain: redis client is required",
		},
		{
			name:    "nil log",
			cfg:     redissub.OrgPublisherConfig{Client: client, ErrPrefix: "mydomain"},
			wantErr: "mydomain: logger is required",
		},
		{
			name:    "nil client default prefix",
			cfg:     redissub.OrgPublisherConfig{Log: log},
			wantErr: "redissub: redis client is required",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			_, err := redissub.NewOrgPublisher(tt.cfg)
			if err == nil {
				t.Fatal("expected error")
			}
			if !strings.Contains(err.Error(), tt.wantErr) {
				t.Fatalf("err=%q want substring %q", err.Error(), tt.wantErr)
			}
		})
	}
}

func TestUnit_OrgPublisher_PublishJSON(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	prefix := "ibex:test:invalidate:"
	org := uuid.New()
	channel := redissub.ChannelForOrg(prefix, org)

	ctx := context.Background()
	pubsub := client.Subscribe(ctx, channel)
	t.Cleanup(func() { _ = pubsub.Close() })
	if _, err := pubsub.Receive(ctx); err != nil {
		t.Fatalf("subscribe: %v", err)
	}

	pub, err := redissub.NewOrgPublisher(redissub.OrgPublisherConfig{
		Client:        client,
		Log:           logger.Discard("redissub-pub"),
		ChannelPrefix: prefix,
		ErrPrefix:     "testdomain",
	})
	if err != nil {
		t.Fatal(err)
	}

	payload := []byte(`{"v":1,"org_id":"` + org.String() + `","epoch":1}`)
	if err := pub.PublishJSON(ctx, org, payload); err != nil {
		t.Fatalf("PublishJSON: %v", err)
	}

	select {
	case msg := <-pubsub.Channel():
		if msg.Channel != channel {
			t.Fatalf("channel=%q want %q", msg.Channel, channel)
		}
		if msg.Payload != string(payload) {
			t.Fatalf("payload=%q want %q", msg.Payload, payload)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for published message")
	}
}
