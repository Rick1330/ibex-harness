package directive_test

import (
	"bytes"
	"context"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/google/uuid"
)

func TestUnit_Resolve_PopulateDroppedAfterShutdown(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	log := mustBufferedLogger(t, &buf)
	store := newFakeStore(directive.Resolved{
		Content: "post-shutdown", InjectionMode: "system_first", VersionID: uuid.New(),
	})
	_, client := newTestRedis(t)
	r, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: store, Config: directive.Config{CacheTTL: time.Minute}, Log: log,
		WriteWorkers: 1, WriteQueue: 1,
	})
	if err != nil {
		t.Fatalf("NewCachedResolver: %v", err)
	}
	if err := r.Shutdown(context.Background()); err != nil {
		t.Fatalf("Shutdown: %v", err)
	}

	orgID, agentID := uuid.New(), uuid.New()
	ctx := reqid.WithRequestID(context.Background(), "req-directive-drop")
	got, err := r.Resolve(ctx, orgID, agentID)
	if err != nil {
		t.Fatalf("Resolve after shutdown: %v", err)
	}
	assertResolvedContent(t, got, "post-shutdown")
	assertStoreLoads(t, store, 1)

	logged := buf.String()
	if !strings.Contains(logged, "directive cache populate dropped") {
		t.Fatalf("expected populate-drop warn, got %s", logged)
	}
	if !strings.Contains(logged, "queue_full_or_shutdown") {
		t.Fatalf("expected drop reason, got %s", logged)
	}
	if !strings.Contains(logged, "req-directive-drop") {
		t.Fatalf("expected request_id in log, got %s", logged)
	}
}

func TestUnit_CachedResolver_ShutdownNilSafe(t *testing.T) {
	t.Parallel()

	var r *directive.CachedResolver
	if err := r.Shutdown(context.Background()); err != nil {
		t.Fatalf("nil receiver: %v", err)
	}
	if err := (&directive.CachedResolver{}).Shutdown(context.Background()); err != nil {
		t.Fatalf("nil pool: %v", err)
	}
}
