//go:build integration

package proxy_test

import (
	"net/http"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
)

func TestSecurity_SEC4_1_RemainingDecrements(t *testing.T) {
	env := rateLimitEnv(t)
	prevRemaining := -1
	for i := 0; i < 3; i++ {
		resp, _ := authProbeGET(t, orgAProbeOpts(env))
		rem := int(parseHeaderInt(t, resp.Header.Get("X-RateLimit-Remaining"), "X-RateLimit-Remaining"))
		resp.Body.Close()
		if prevRemaining >= 0 && rem >= prevRemaining {
			t.Fatalf("remaining did not decrement: prev=%d cur=%d", prevRemaining, rem)
		}
		prevRemaining = rem
	}
}

func TestSecurity_SEC4_2_BurstReturns429(t *testing.T) {
	env := rateLimitEnv(t)
	resp, body := lastBurstProbe(t, env)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusTooManyRequests {
		t.Fatalf("burst status=%d body=%s", resp.StatusCode, body)
	}
	requireErrorCode(t, body, apierror.CodeRateLimited)
	assertSecurityErrorEnvelope(t, resp, body, env.orgA.Token)
}

func TestSecurity_SEC4_3_RetryAfterHeader(t *testing.T) {
	env := rateLimitEnv(t)
	resp, _ := lastBurstProbe(t, env)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusTooManyRequests {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	ra := parseRetryAfter(t, resp.Header.Get("Retry-After"))
	if ra <= 0 || ra > 60 {
		t.Fatalf("Retry-After out of range: %d", ra)
	}
}

func TestSecurity_SEC4_4_ResetHeader(t *testing.T) {
	env := rateLimitEnv(t)
	resp, _ := lastBurstProbe(t, env)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusTooManyRequests {
		t.Fatalf("status=%d", resp.StatusCode)
	}
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

func TestSecurity_SEC4_6_RedisFailOpen(t *testing.T) {
	env := rateLimitEnv(t)
	env.redisMR.Close()
	requireProbeOK(t, orgAProbeOpts(env))
}
