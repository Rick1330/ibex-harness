//go:build integration

package proxy_test

import (
	"context"
	"net/http"
	"sync/atomic"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/provider"
)

type outageCountingProvider struct{ calls atomic.Int64 }

func (*outageCountingProvider) Name() string { return "outage-counting" }

func (*outageCountingProvider) SupportedModels() []string { return []string{"gpt-4o"} }

func (p *outageCountingProvider) Complete(ctx context.Context, req provider.Request) (provider.Response, error) {
	p.calls.Add(1)
	return mockForwardingProvider{}.Complete(ctx, req)
}

func TestSecurity_SEC4_1_RemainingDecrements(t *testing.T) {
	env := rateLimitEnv(t)
	decreases := 0
	lastRemaining := -1
	// Calendar-minute Redis windows can roll mid-test; restart the baseline
	// on rollover and require two strict decreases within one window.
	for attempts := 0; attempts < 24 && decreases < 2; attempts++ {
		resp, body := authProbeGET(t, orgAProbeOpts(env))
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("auth probe status=%d body=%s", resp.StatusCode, body)
		}
		rem := int(parseHeaderInt(t, resp.Header.Get("X-RateLimit-Remaining"), "X-RateLimit-Remaining"))
		resp.Body.Close()
		if lastRemaining < 0 {
			lastRemaining = rem
			continue
		}
		if rem > lastRemaining {
			// New minute window: restart with a fresh decrement count.
			lastRemaining = rem
			decreases = 0
			continue
		}
		if rem == lastRemaining {
			// Under parallel CI, hierarchical remaining can lag one probe;
			// keep sampling instead of failing the whole suite on a tie.
			time.Sleep(20 * time.Millisecond)
			continue
		}
		lastRemaining = rem
		decreases++
	}
	if decreases < 2 {
		t.Fatalf("expected 2 remaining decreases within one minute window, got %d", decreases)
	}
}

func TestSecurity_SEC4_2_BurstReturns429(t *testing.T) {
	env := rateLimitEnv(t)
	resp, body := requireRateLimitedProbe(t, env)
	defer resp.Body.Close()
	requireErrorCode(t, body, apierror.CodeRateLimited)
	assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
}

func TestSecurity_SEC4_3_RetryAfterHeader(t *testing.T) {
	env := rateLimitEnv(t)
	resp, _ := requireRateLimitedProbe(t, env)
	defer resp.Body.Close()
	ra := parseRetryAfter(t, resp.Header.Get("Retry-After"))
	if ra <= 0 || ra > 60 {
		t.Fatalf("Retry-After out of range: %d", ra)
	}
}

func TestSecurity_SEC4_4_ResetHeader(t *testing.T) {
	env := rateLimitEnv(t)
	resp, _ := requireRateLimitedProbe(t, env)
	defer resp.Body.Close()
	reset := parseResetUnix(t, resp.Header.Get("X-RateLimit-Reset"))
	now := time.Now().Unix()
	if reset < now || reset > now+60 {
		t.Fatalf("X-RateLimit-Reset out of range: reset=%d now=%d", reset, now)
	}
}

func TestSecurity_SEC4_5_PerOrgIsolation(t *testing.T) {
	env := rateLimitEnv(t)
	exhaustOrgARateLimit(t, env)
	resp, _ := authProbeGET(t, authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgB.Token, agentID: env.orgB.AgentID})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("org B status=%d after org A exhaustion", resp.StatusCode)
	}
}

func TestSecurity_SEC4_6_RedisOutageFailsClosed(t *testing.T) {
	env := rateLimitEnv(t)
	env.redisMR.Close()
	resp, body := authProbeGET(t, orgAProbeOpts(env))
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("status=%d want=%d body=%s", resp.StatusCode, http.StatusServiceUnavailable, body)
	}
	requireErrorCode(t, body, apierror.CodeServiceDegraded)
	if got := resp.Header.Get("Retry-After"); got != "5" {
		t.Fatalf("Retry-After=%q want 5 seconds", got)
	}
}

func TestSecurity_SEC4_7_RedisOutageBlocksChatProviderWork(t *testing.T) {
	providerCounter := &outageCountingProvider{}
	env := setupSecurityTestEnv(t, proxyServerOpts{
		defaultRPM: rateLimitBurstRPM,
		providers:  []provider.Provider{providerCounter},
	})
	env.redisMR.Close()

	resp, body := chatPOST(t, chatRequestOpts{
		srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgA.AgentID,
		contentType: "application/json", body: minimalChatBody,
	})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("status=%d want=%d body=%s", resp.StatusCode, http.StatusServiceUnavailable, body)
	}
	requireErrorCode(t, body, apierror.CodeServiceDegraded)
	if got := resp.Header.Get("Retry-After"); got != "5" {
		t.Fatalf("Retry-After=%q want 5 seconds", got)
	}
	assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
	if got := providerCounter.calls.Load(); got != 0 {
		t.Fatalf("provider was invoked %d times during Redis outage; want 0", got)
	}
}
