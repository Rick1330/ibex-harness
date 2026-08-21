package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

const selfHostedModelsPath = "/models"

// waitSelfHostedReady polls GET {base}/models until 2xx or timeout (fail-closed at boot).
func waitSelfHostedReady(ctx context.Context, baseURL string, sh config.SelfHostedConfig, log *logger.Logger) error {
	timeout, poll := selfHostedProbeTiming(sh)
	deadline := time.Now().Add(timeout)
	ctx, cancel := context.WithDeadline(ctx, deadline)
	defer cancel()

	client := &http.Client{Timeout: 5 * time.Second}
	url := strings.TrimRight(baseURL, "/") + selfHostedModelsPath

	for attempt := 1; ; attempt++ {
		ok, probeErr := probeModels(ctx, client, url, sh.APIKey)
		if ok {
			log.InfoCtx(ctx, "selfhosted_ready", "url", url, "attempts", attempt)
			return nil
		}
		if errors.Is(probeErr, context.DeadlineExceeded) || errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return readinessTimeoutError(timeout, probeErr)
		}
		if err := waitOrTimeout(ctx, deadline, timeout, poll, url, attempt, probeErr, log); err != nil {
			return err
		}
	}
}

func selfHostedProbeTiming(sh config.SelfHostedConfig) (timeout, poll time.Duration) {
	timeout = sh.ReadyTimeout
	if timeout <= 0 {
		timeout = 60 * time.Second
	}
	poll = sh.ReadyPoll
	if poll <= 0 {
		poll = 2 * time.Second
	}
	return timeout, poll
}

func waitOrTimeout(
	ctx context.Context,
	deadline time.Time,
	timeout, poll time.Duration,
	url string,
	attempt int,
	probeErr error,
	log *logger.Logger,
) error {
	wait := remainingPoll(deadline, poll)
	if wait <= 0 {
		return readinessTimeoutError(timeout, probeErr)
	}
	log.WarnCtx(ctx, "selfhosted_not_ready", "url", url, "attempt", attempt, "err", errString(probeErr))
	select {
	case <-ctx.Done():
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return readinessTimeoutError(timeout, probeErr)
		}
		return ctx.Err()
	case <-time.After(wait):
		return nil
	}
}

func remainingPoll(deadline time.Time, poll time.Duration) time.Duration {
	left := time.Until(deadline)
	if left <= 0 {
		return 0
	}
	if poll < left {
		return poll
	}
	return left
}

func readinessTimeoutError(timeout time.Duration, probeErr error) error {
	if probeErr != nil {
		return fmt.Errorf("self-hosted readiness probe failed after %s: %w", timeout, probeErr)
	}
	return fmt.Errorf("self-hosted readiness probe failed after %s: non-success response", timeout)
}

func probeModels(ctx context.Context, client *http.Client, url, apiKey string) (bool, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return false, err
	}
	applyOptionalBearer(req, apiKey)
	resp, err := client.Do(req)
	if err != nil {
		return false, err
	}
	defer func() { _ = resp.Body.Close() }()
	_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		return true, nil
	}
	return false, fmt.Errorf("status %d", resp.StatusCode)
}

func applyOptionalBearer(req *http.Request, apiKey string) {
	if key := strings.TrimSpace(apiKey); key != "" {
		req.Header.Set("Authorization", "Bearer "+key)
	}
}

func errString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}

// newSelfHostedReadyChecker returns an advisory /ready dependency for self-hosted.
func newSelfHostedReadyChecker(baseURL, apiKey string) func(context.Context) error {
	client := &http.Client{Timeout: 3 * time.Second}
	url := strings.TrimRight(baseURL, "/") + selfHostedModelsPath
	return func(ctx context.Context) error {
		ok, err := probeModels(ctx, client, url, apiKey)
		if ok {
			return nil
		}
		if err != nil {
			return err
		}
		return fmt.Errorf("self-hosted models probe unsuccessful")
	}
}
