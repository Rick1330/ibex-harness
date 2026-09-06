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
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	agent := uuid.MustParse("22222222-2222-2222-2222-222222222222")
	got := extractionbuffer.Key(extractionbuffer.LookupKey{OrgID: org, AgentID: agent, ExternalID: "ext-1"})
	want := "11111111-1111-1111-1111-111111111111:session:22222222-2222-2222-2222-222222222222:ext-1:extraction_turns"
	if got != want {
		t.Fatalf("key=%q want %q", got, want)
	}
}

func TestUnit_AppendTake(t *testing.T) {
	t.Parallel()
	b, _ := testBuffer(t)
	k := extractionbuffer.LookupKey{OrgID: uuid.New(), AgentID: uuid.New(), ExternalID: "e1"}
	mustAppendOK(t, b, k, []extractionbuffer.Turn{
		{TurnIndex: 0, Role: "user", Content: "hi"},
		{TurnIndex: 1, Role: "assistant", Content: "hello"},
	})
	assertTakeLen(t, b, k, 2)
	assertTakeLen(t, b, k, 0)
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
	if err != nil {
		t.Fatal(err)
	}
	if out != extractionbuffer.AppendCap {
		t.Fatalf("outcome=%v", out)
	}
	assertTakeLen(t, b, k, extractionbuffer.MaxTurnsPerBatch)
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
	assertTurn(t, got, 0, 6, "u2")
	assertTurn(t, got, 1, 7, "a")
}

func TestUnit_AppendConcurrentNoLostTurns(t *testing.T) {
	t.Parallel()
	b, _ := testBuffer(t)
	k := extractionbuffer.LookupKey{OrgID: uuid.New(), AgentID: uuid.New(), ExternalID: "race"}
	const workers = 20
	fanoutAppend(t, b, k, workers)
	assertPeekLen(t, b, k, workers)
	if err := b.Ack(context.Background(), k); err != nil {
		t.Fatal(err)
	}
	assertPeekLen(t, b, k, 0)
}

func fanoutAppend(t *testing.T, b *extractionbuffer.Buffer, k extractionbuffer.LookupKey, workers int) {
	t.Helper()
	errs := make(chan error, workers)
	for i := 0; i < workers; i++ {
		i := i
		go func() {
			errs <- appendOne(b, k, i)
		}()
	}
	for i := 0; i < workers; i++ {
		if err := <-errs; err != nil {
			t.Fatalf("append: %v", err)
		}
	}
}

func appendOne(b *extractionbuffer.Buffer, k extractionbuffer.LookupKey, i int) error {
	out, err := b.Append(context.Background(), k, []extractionbuffer.Turn{
		{TurnIndex: i, Role: "user", Content: fmt.Sprintf("m-%d", i)},
	})
	if err != nil {
		return err
	}
	if out != extractionbuffer.AppendOK && out != extractionbuffer.AppendCap {
		return fmt.Errorf("outcome=%s", out)
	}
	return nil
}

func mustAppendOK(t *testing.T, b *extractionbuffer.Buffer, k extractionbuffer.LookupKey, turns []extractionbuffer.Turn) {
	t.Helper()
	out, err := b.Append(context.Background(), k, turns)
	if err != nil {
		t.Fatal(err)
	}
	if out != extractionbuffer.AppendOK {
		t.Fatalf("outcome=%v", out)
	}
}

func assertTakeLen(t *testing.T, b *extractionbuffer.Buffer, k extractionbuffer.LookupKey, want int) {
	t.Helper()
	turns, err := b.Take(context.Background(), k)
	if err != nil {
		t.Fatal(err)
	}
	if len(turns) != want {
		t.Fatalf("take len=%d want %d", len(turns), want)
	}
}

func assertPeekLen(t *testing.T, b *extractionbuffer.Buffer, k extractionbuffer.LookupKey, want int) {
	t.Helper()
	turns, err := b.Peek(context.Background(), k)
	if err != nil {
		t.Fatal(err)
	}
	if len(turns) != want {
		t.Fatalf("peek len=%d want %d", len(turns), want)
	}
}

func assertTurn(t *testing.T, got []extractionbuffer.Turn, idx, turnIndex int, content string) {
	t.Helper()
	if idx >= len(got) {
		t.Fatalf("missing turn idx=%d", idx)
	}
	if got[idx].TurnIndex != turnIndex {
		t.Fatalf("turn_index=%d want %d", got[idx].TurnIndex, turnIndex)
	}
	if got[idx].Content != content {
		t.Fatalf("content=%q want %q", got[idx].Content, content)
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
