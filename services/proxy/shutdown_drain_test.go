package proxy_test

import (
	"context"
	"io"
	"log/slog"
	"net"
	"net/http"
	"os"
	"sync/atomic"
	"syscall"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/shutdown"
)

func TestShutdownDrainsSlowHandler(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	var handlerDone atomic.Bool
	handlerStarted := make(chan struct{})

	server := &http.Server{
		Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			close(handlerStarted)
			time.Sleep(150 * time.Millisecond)
			handlerDone.Store(true)
			w.WriteHeader(http.StatusOK)
		}),
	}

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	server.Addr = ln.Addr().String()

	go func() {
		_ = server.Serve(ln)
	}()

	sigCh := make(chan os.Signal, 1)
	coord := shutdown.NewWithSignalChan(5*time.Second, logger, sigCh)
	coord.Register(func(ctx context.Context) error {
		return server.Shutdown(ctx)
	})

	reqDone := make(chan struct{})
	go func() {
		defer close(reqDone)
		resp, err := http.Get("http://" + ln.Addr().String() + "/")
		if err != nil {
			return
		}
		_ = resp.Body.Close()
	}()

	select {
	case <-handlerStarted:
	case <-time.After(2 * time.Second):
		t.Fatal("handler did not start")
	}

	go func() {
		sigCh <- syscall.SIGTERM
	}()

	if err := coord.Wait(); err != nil {
		t.Fatalf("Wait: %v", err)
	}
	<-reqDone
	if !handlerDone.Load() {
		t.Fatal("in-flight handler should complete during drain")
	}
}
