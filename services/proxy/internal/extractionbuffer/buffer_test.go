package extractionbuffer_test

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionbuffer"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func TestUnit_Key(t *testing.T) {
	t.Parallel()
	org, agent := uuid.MustParse("11111111-1111-1111-1111-111111111111"), uuid.MustParse("22222222-2222-2222-2222-222222222222")
	got := extractionbuffer.Key(extractionbuffer.LookupKey{OrgID: org, AgentID: agent, ExternalID: "ext-1"})
	want := "11111111-1111-1111-1111-111111111111:session:22222222-2222-2222-2222-222222222222:ext-1:extraction_turns"
	if got != want {
		t.Fatalf("key=%q want %q", got, want)
	}
}

func TestUnit_AppendTake(t *testing.T) {
	t.Parallel()
	b, mr := testBuffer(t)
	k := extractionbuffer.LookupKey{OrgID: uuid.New(), AgentID: uuid.New(), ExternalID: "e1"}
	out, err := b.Append(context.Background(), k, []extractionbuffer.Turn{
		{TurnIndex: 0, Role: "user", Content: "hi"},
		{TurnIndex: 1, Role: "assistant", Content: "hello"},
	})
	if err != nil || out != extractionbuffer.AppendOK {
		t.Fatalf("append: %v %v", out, err)
	}
	turns, err := b.Take(context.Background(), k)
	if err != nil || len(turns) != 2 {
		t.Fatalf("take: %v %#v", err, turns)
	}
	turns, err = b.Take(context.Background(), k)
	if err != nil || len(turns) != 0 {
		t.Fatalf("second take: %v %#v", err, turns)
	}
	_ = mr
}

func TestUnit_AppendCap(t *testing.T) {
	t.Parallel()
	b, _ := testBuffer(t)
	k := extractionbuffer.LookupKey{OrgID: uuid.New(), AgentID: uuid.New(), ExternalID: "cap"}
	turns := make([]extractionbuffer.Turn, 0, extractionbuffer.MaxTurnsPerBatch+2)
	for i := 0; i < extractionbuffer.MaxTurnsPerBatch+2; i++ {
		turns = append(turns, extractionbuffer.Turn{TurnIndex: i, Role: "user", Content: "x"})
	}
	out, err := b.Append(context.Background(), k, turns)
	if err != nil || out != extractionbuffer.AppendCap {
		t.Fatalf("want cap, got %v %v", out, err)
	}
	got, err := b.Take(context.Background(), k)
	if err != nil || len(got) != extractionbuffer.MaxTurnsPerBatch {
		t.Fatalf("len=%d err=%v", len(got), err)
	}
}

func TestUnit_AppendFailOpenClosedClient(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	b, err := extractionbuffer.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	mr.Close()
	out, aerr := b.Append(context.Background(), extractionbuffer.LookupKey{
		OrgID: uuid.New(), AgentID: uuid.New(), ExternalID: "e",
	}, []extractionbuffer.Turn{{TurnIndex: 0, Role: "user", Content: "hi"}})
	if out != extractionbuffer.AppendRedisErr {
		t.Fatalf("outcome=%v", out)
	}
	if aerr == nil {
		t.Fatal("expected redis error")
	}
}

func TestUnit_TurnsFromChat(t *testing.T) {
	t.Parallel()
	got := extractionbuffer.TurnsFromChat(3, "u2", "a")
	if len(got) != 2 {
		t.Fatalf("len=%d %#v", len(got), got)
	}
	if got[0].TurnIndex != 6 || got[0].Content != "u2" {
		t.Fatalf("user turn %#v", got[0])
	}
	if got[1].TurnIndex != 7 {
		t.Fatalf("assistant turn %#v", got[1])
	}
}

func TestUnit_AppendConcurrentNoLostTurns(t *testing.T) {
	t.Parallel()
	b, _ := testBuffer(t)
	k := extractionbuffer.LookupKey{OrgID: uuid.New(), AgentID: uuid.New(), ExternalID: "race"}
	const workers = 20
	errs := make(chan error, workers)
	for i := 0; i < workers; i++ {
		i := i
		go func() {
			out, err := b.Append(context.Background(), k, []extractionbuffer.Turn{
				{TurnIndex: i, Role: "user", Content: fmt.Sprintf("m-%d", i)},
			})
			if err != nil {
				errs <- err
				return
			}
			if out != extractionbuffer.AppendOK && out != extractionbuffer.AppendCap {
				errs <- fmt.Errorf("outcome=%s", out)
				return
			}
			errs <- nil
		}()
	}
	for i := 0; i < workers; i++ {
		if err := <-errs; err != nil {
			t.Fatalf("append: %v", err)
		}
	}
	turns, err := b.Peek(context.Background(), k)
	if err != nil {
		t.Fatal(err)
	}
	if len(turns) != workers {
		t.Fatalf("lost turns: got %d want %d", len(turns), workers)
	}
	if err := b.Ack(context.Background(), k); err != nil {
		t.Fatal(err)
	}
	turns, err = b.Peek(context.Background(), k)
	if err != nil {
		t.Fatal(err)
	}
	if len(turns) != 0 {
		t.Fatalf("after ack len=%d", len(turns))
	}
}

func testBuffer(t *testing.T) (*extractionbuffer.Buffer, *miniredis.Miniredis) {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	b, err := extractionbuffer.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	return b, mr
}
