package bootstrap

import (
	"context"
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
	timeout := sh.ReadyTimeout
	if timeout <= 0 {
		timeout = 60 * time.Second
	}
	poll := sh.ReadyPoll
	if poll <= 0 {
		poll = 2 * time.Second
	}
	deadline := time.Now().Add(timeout)
	client := &http.Client{Timeout: 5 * time.Second}
	url := strings.TrimRight(baseURL, "/") + selfHostedModelsPath
	attempt := 0
	for {
		attempt++
		ok, err := probeModels(ctx, client, url, sh.APIKey)
		if ok {
			log.InfoCtx(ctx, "selfhosted_ready", "url", url, "attempts", attempt)
			return nil
		}
		if time.Now().After(deadline) {
			if err != nil {
				return fmt.Errorf("self-hosted readiness probe failed after %s: %w", timeout, err)
			}
			return fmt.Errorf("self-hosted readiness probe failed after %s: non-success response", timeout)
		}
		log.WarnCtx(ctx, "selfhosted_not_ready", "url", url, "attempt", attempt, "err", errString(err))
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(poll):
		}
	}
}

func probeModels(ctx context.Context, client *http.Client, url, apiKey string) (bool, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return false, err
	}
	if key := strings.TrimSpace(apiKey); key != "" {
		req.Header.Set("Authorization", "Bearer "+key)
	}
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
