package bootstrap

import (
	"context"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/redissub"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func TestUnit_StopSubscribersOnFailure_InvokesAllCleanups(t *testing.T) {
	t.Parallel()

	var (
		revCancelN, dirCancelN, rlCancelN atomic.Int32
		mpCancelN, mpPollN, budgetCancelN atomic.Int32
	)

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	log := logger.Discard("wire-subs")

	dirSub, dirCancel := mustStartDirectiveSub(t, client, log)
	budgetSub, budgetCancel := mustStartBudgetSub(t, client, log)

	stopSubscribersOnFailure(startedSubscribers{
		revCancel: func() { revCancelN.Add(1) },
		dirSub:    dirSub,
		dirCancel: func() {
			dirCancelN.Add(1)
			dirCancel()
		},
		rlCancel: func() { rlCancelN.Add(1) },
		mpCancel: func() { mpCancelN.Add(1) },
		mpPollCancel: func() {
			mpPollN.Add(1)
		},
		budgetSub: budgetSub,
		budgetCancel: func() {
			budgetCancelN.Add(1)
			budgetCancel()
		},
	})

	assertCancelFired(t, "rev", revCancelN.Load(), 1)
	assertCancelFired(t, "dir", dirCancelN.Load(), 1)
	assertCancelFired(t, "rl", rlCancelN.Load(), 1)
	assertCancelFired(t, "mp", mpCancelN.Load(), 1)
	assertCancelFired(t, "mpPoll", mpPollN.Load(), 1)
	assertCancelFired(t, "budget", budgetCancelN.Load(), 1)

	waitSubscriberDone(t, "directive", dirSub.Done())
	waitSubscriberDone(t, "budget", budgetSub.Done())
}

func TestUnit_StopBudgetOnFailure_NilSafe(t *testing.T) {
	t.Parallel()
	stopBudgetOnFailure(nil, nil)
	var canceled atomic.Bool
	stopBudgetOnFailure(nil, func() { canceled.Store(true) })
	if !canceled.Load() {
		t.Fatal("expected cancel")
	}
}

func TestUnit_StopDirectiveOnFailure_NilSafe(t *testing.T) {
	t.Parallel()
	stopDirectiveOnFailure(nil, nil)
	var canceled atomic.Bool
	stopDirectiveOnFailure(nil, func() { canceled.Store(true) })
	if !canceled.Load() {
		t.Fatal("expected cancel")
	}
}

func TestUnit_CloseProxyGRPCConns_BestEffort(t *testing.T) {
	t.Parallel()

	closeProxyGRPCConns(nil)
	closeProxyGRPCConns([]*grpc.ClientConn{})

	conn, err := grpc.NewClient("127.0.0.1:1", grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	closeProxyGRPCConns([]*grpc.ClientConn{conn})
	closeProxyGRPCConns([]*grpc.ClientConn{conn})
}

func TestUnit_StartBudgetSubscriber_NilLoggerFails(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	_, _, err := startBudgetSubscriber(client, mustBudgetCache(t), nil, nil)
	if err == nil {
		t.Fatal("expected logger-required error")
	}
	if !strings.Contains(err.Error(), "logger") {
		t.Fatalf("err=%v", err)
	}
}

func TestUnit_StartProxySubscribers_BudgetFailureRollsBackPrior(t *testing.T) {
	t.Parallel()

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	log := logger.Discard("wire-budget-fail")
	dirResolver := mustCachedDirective(t, client, log)

	dirSub, dirCancel, err := startDirectiveSubscriber(client, dirResolver, log, nil)
	if err != nil || dirSub == nil {
		t.Fatalf("dir start: sub=%v err=%v", dirSub, err)
	}

	// Mirror startProxySubscribers budget-failure branch: stop prior subscribers.
	_, _, budgetErr := startBudgetSubscriber(client, mustBudgetCache(t), nil, nil)
	if budgetErr == nil {
		t.Fatal("expected budget start failure with nil logger")
	}
	stopSubscribersOnFailure(startedSubscribers{
		dirSub: dirSub, dirCancel: dirCancel,
	})
	waitSubscriberDone(t, "prior directive", dirSub.Done())
}

func TestUnit_StartProxySubscribers_StartsBudgetThenCleanup(t *testing.T) {
	t.Parallel()

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	log := logger.Discard("wire-budget-ok")

	rlLim, err := ratelimit.NewHierarchicalLimiter(client, ratelimit.HierarchicalConfig{
		DefaultRPM: 60, GlobalRPM: 1000,
	})
	if err != nil {
		t.Fatal(err)
	}
	assembled := assembledProxyCore{
		redisClient:       client,
		validator:         stubTokenValidator{},
		directiveResolver: mustCachedDirective(t, client, log),
		limiter:           rlLim,
		budgetCache:       mustBudgetCache(t),
	}
	subs, err := startProxySubscribers(assembled, setupProxyCoreInput{log: log})
	if err != nil {
		t.Fatalf("startProxySubscribers: %v", err)
	}
	if subs.budgetSub == nil || subs.budgetCancel == nil {
		t.Fatal("expected budget subscriber")
	}
	if subs.dirSub == nil {
		t.Fatal("expected directive subscriber")
	}
	stopSubscribersOnFailure(subs)
	waitSubscriberDone(t, "budget", subs.budgetSub.Done())
	waitSubscriberDone(t, "directive", subs.dirSub.Done())
}

func assertCancelFired(t *testing.T, name string, got, want int32) {
	t.Helper()
	if got != want {
		t.Fatalf("%s=%d want %d", name, got, want)
	}
}

func waitSubscriberDone(t *testing.T, name string, done <-chan struct{}) {
	t.Helper()
	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatalf("%s did not stop", name)
	}
}

func mustCachedDirective(t *testing.T, client redis.UniversalClient, log *logger.Logger) *directive.CachedResolver {
	t.Helper()
	resolver, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: staticDirectiveLoader{},
		Config: directive.Config{CacheTTL: time.Minute}, Log: log,
	})
	if err != nil {
		t.Fatal(err)
	}
	return resolver
}

func mustStartDirectiveSub(t *testing.T, client *redis.Client, log *logger.Logger) (*directive.Subscriber, context.CancelFunc) {
	t.Helper()
	sub, cancel, err := startDirectiveSubscriber(client, mustCachedDirective(t, client, log), log, nil)
	return requireStarted(t, "directive", sub, cancel, err)
}

func mustStartBudgetSub(t *testing.T, client *redis.Client, log *logger.Logger) (*redissub.OrgSubscriber, context.CancelFunc) {
	t.Helper()
	sub, cancel, err := startBudgetSubscriber(client, mustBudgetCache(t), log, nil)
	return requireStarted(t, "budget", sub, cancel, err)
}

func requireStarted[T any](t *testing.T, name string, sub T, cancel context.CancelFunc, err error) (T, context.CancelFunc) {
	t.Helper()
	if err != nil {
		t.Fatalf("%s start: %v", name, err)
	}
	v := reflect.ValueOf(sub)
	if !v.IsValid() || ((v.Kind() == reflect.Pointer || v.Kind() == reflect.Interface) && v.IsNil()) {
		t.Fatalf("%s subscriber nil", name)
	}
	if cancel == nil {
		t.Fatalf("%s cancel nil", name)
	}
	return sub, cancel
}
