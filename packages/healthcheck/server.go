package healthcheck

import (
	"context"
	"encoding/json"
	"net/http"
	"sync"
	"time"
)

const (
	defaultOverallTimeout  = 750 * time.Millisecond
	defaultPerCheckTimeout = 500 * time.Millisecond

	statusOK        = "ok"
	statusDegraded  = "degraded"
	statusUnhealthy = "unhealthy"
	checkOK         = "ok"
	checkFailed     = "failed"
)

// Server runs /health and /ready HTTP handlers from registered checkers.
type Server struct {
	CriticalCheckers map[string]Checker
	AdvisoryCheckers map[string]Checker
	OverallTimeout   time.Duration
	PerCheckTimeout  time.Duration
}

// HealthHandler returns a liveness handler: 200 with no external checks.
func (s *Server) HealthHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if rejectNonGet(w, r) {
			return
		}
		writeJSON(w, http.StatusOK, Response{Status: statusOK, Checks: map[string]Check{}})
	}
}

// ReadyHandler returns a readiness handler that runs critical and advisory checkers.
func (s *Server) ReadyHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if rejectNonGet(w, r) {
			return
		}

		overall := s.overallTimeout()
		ctx, cancel := context.WithTimeout(r.Context(), overall)
		defer cancel()

		perCheck := s.perCheckTimeout()
		checks := runCheckers(ctx, perCheck, s.CriticalCheckers, s.AdvisoryCheckers)
		status, httpStatus := readinessStatus(checks, s.CriticalCheckers, s.AdvisoryCheckers)
		writeJSON(w, httpStatus, Response{Status: status, Checks: checks})
	}
}

func (s *Server) overallTimeout() time.Duration {
	if s.OverallTimeout > 0 {
		return s.OverallTimeout
	}
	return defaultOverallTimeout
}

func (s *Server) perCheckTimeout() time.Duration {
	if s.PerCheckTimeout > 0 {
		return s.PerCheckTimeout
	}
	return defaultPerCheckTimeout
}

func runCheckers(ctx context.Context, perCheck time.Duration, groups ...map[string]Checker) map[string]Check {
	total := 0
	for _, g := range groups {
		total += len(g)
	}
	if total == 0 {
		return map[string]Check{}
	}

	results := make(map[string]Check, total)
	var mu sync.Mutex
	var wg sync.WaitGroup

	for _, group := range groups {
		for name, checker := range group {
			wg.Add(1)
			go func(name string, checker Checker) {
				defer wg.Done()
				result := runOneCheck(ctx, perCheck, checker)
				mu.Lock()
				results[name] = result
				mu.Unlock()
			}(name, checker)
		}
	}
	wg.Wait()
	return results
}

func runOneCheck(ctx context.Context, perCheck time.Duration, checker Checker) Check {
	checkCtx, cancel := context.WithTimeout(ctx, perCheck)
	defer cancel()

	start := time.Now()
	err := checker(checkCtx)
	latency := time.Since(start).Milliseconds()
	if err == nil {
		return Check{Status: checkOK, LatencyMs: latency}
	}
	return Check{Status: checkFailed, Message: err.Error(), LatencyMs: latency}
}

func readinessStatus(checks map[string]Check, critical, advisory map[string]Checker) (string, int) {
	if anyFailed(checks, critical) {
		return statusUnhealthy, http.StatusServiceUnavailable
	}
	if anyFailed(checks, advisory) {
		return statusDegraded, http.StatusOK
	}
	return statusOK, http.StatusOK
}

func anyFailed(checks map[string]Check, group map[string]Checker) bool {
	for name := range group {
		if c, ok := checks[name]; ok && c.Status == checkFailed {
			return true
		}
	}
	return false
}

func rejectNonGet(w http.ResponseWriter, r *http.Request) bool {
	if r.Method == http.MethodGet {
		return false
	}
	w.Header().Set("Allow", http.MethodGet)
	writeJSON(w, http.StatusMethodNotAllowed, Response{Status: statusUnhealthy, Checks: map[string]Check{}})
	return true
}

func writeJSON(w http.ResponseWriter, status int, body Response) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
