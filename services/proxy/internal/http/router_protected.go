package http

import (
	"net/http"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

type protectedRouteDeps struct {
	mux              *http.ServeMux
	cfg              config.Config
	logger           *logger.Logger
	reg              *metrics.ProxyRegistry
	validator        auth.TokenValidator
	agentVerifier    auth.AgentVerifier
	limiter          ratelimit.Limiter
	docsBase         string
	providerRegistry *provider.Registry
}

func registerProtectedRoutes(deps protectedRouteDeps) {
	var rateLimit func(http.Handler) http.Handler
	if deps.limiter != nil {
		rateLimit = RateLimitMiddleware(deps.limiter, deps.logger, deps.reg)
	}
	var agentVerify func(http.Handler) http.Handler
	if deps.agentVerifier != nil {
		agentVerify = AgentVerificationMiddleware(deps.agentVerifier, deps.logger)
	}

	authNone := AuthMiddleware(deps.validator, deps.logger, AuthOptions{})
	deps.mux.Handle("/v1/internal/auth-probe", chain(authNone, agentVerify, rateLimit)(http.HandlerFunc(handleAuthProbe)))

	authOrg := func(orgID string) func(http.Handler) http.Handler {
		return AuthMiddleware(deps.validator, deps.logger, AuthOptions{PathOrgID: orgID})
	}
	deps.mux.HandleFunc("/v1/orgs/{org_id}/auth-probe", func(w http.ResponseWriter, r *http.Request) {
		if !requireMethod(w, r, http.MethodGet, deps.docsBase) {
			return
		}
		orgID := strings.TrimSpace(r.PathValue("org_id"))
		chain(
			PathOrgUUIDMiddleware(deps.docsBase),
			authOrg(orgID),
			agentVerify,
			rateLimit,
		)(http.HandlerFunc(handleAuthProbe)).ServeHTTP(w, r)
	})

	chatChain := chain(
		BodySizeLimitMiddleware(deps.cfg.MaxRequestBodyBytes, deps.docsBase),
		ContentTypeMiddleware(deps.docsBase),
		AuthMiddleware(deps.validator, deps.logger, AuthOptions{RequireProxyChatCompletion: true}),
		agentVerify,
		rateLimit,
	)
	deps.mux.Handle("/v1/chat/completions", chatChain(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handleChatCompletions(w, r, chatCompletionHandler{
			log:         deps.logger,
			docsBase:    deps.docsBase,
			providerReg: deps.providerRegistry,
		})
	})))
}
