package http

import (
	"net/http"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/Rick1330/ibex-harness/packages/policysnapshot"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/providercap"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/responsepipeline"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionbuffer"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionenqueue"
	httpsession "github.com/Rick1330/ibex-harness/services/proxy/internal/http/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
)

type protectedRouteDeps struct {
	mux                      *http.ServeMux
	cfg                      config.Config
	logger                   *logger.Logger
	reg                      *metrics.ProxyRegistry
	validator                TokenValidator
	agentVerifier            AgentVerifier
	policyFetcher            PolicySnapshotFetcher
	policyVerifier           *policysnapshot.Verifier
	limiter                  ratelimit.Limiter
	budgetCache              *billing.Cache
	usageFactWriter          *billing.UsageFactWriter
	directiveResolver        directive.Resolver
	sessionStore             session.Store
	sessionCache             *sessioncache.Cache
	checkpointPool           *asyncpool.Pool
	getOrCreateTimeout       time.Duration
	evidenceStore            httpsession.EvidencePersister
	docsBase                 string
	providerRegistry         *provider.Registry
	capabilityManifest       *providercap.Snapshot
	modelRouter              ProviderResolver
	agentDefaults            modelpolicy.AgentDefaultLoader
	responsePipeline         *responsepipeline.Pipeline
	traceWriter              TraceWriter
	idempotencyStore         idempotency.Store
	terminationLedger        idempotency.Ledger
	idempotencyTimeout       time.Duration
	idempotencyCommitTimeout time.Duration
	contextClient            contextAssembler
	contextEnabled           bool
	turnBuffer               *extractionbuffer.Buffer
	extractionEnqueue        *extractionenqueue.Client
	credentialResolver       credentialResolver
}

type routeMiddleware = func(http.Handler) http.Handler

// routeMiddlewares bundles the protected-route middleware stages so route
// registration stays under the function-argument budget.
type routeMiddlewares struct {
	rateLimit      routeMiddleware
	agentVerify    routeMiddleware
	policyMutation routeMiddleware
	policyRead     routeMiddleware
	budget         routeMiddleware
}

func registerProtectedRoutes(deps protectedRouteDeps) {
	mw := protectedAuthWrappers(deps)
	registerAuthProbeRoutes(deps, mw)
	registerChatCompletionsRoute(deps, mw)
	registerResponsesRoute(deps, mw)
	registerSessionTerminateRoute(deps, mw)
}

func registerSessionTerminateRoute(deps protectedRouteDeps, mw routeMiddlewares) {
	termChain := chain(
		BodySizeLimitMiddleware(deps.cfg.MaxRequestBodyBytes, deps.docsBase),
		ContentTypeMiddleware(deps.docsBase),
		AuthMiddleware(deps.validator, deps.logger, AuthOptions{
			RequireSessionTerminate: true,
			Metrics:                 deps.reg,
		}),
		mw.agentVerify,
		mw.policyMutation,
		mw.rateLimit,
	)
	h := sessionTerminateHandler{
		store: deps.sessionStore, buffer: deps.turnBuffer, enqueue: deps.extractionEnqueue,
		log: deps.logger, metrics: deps.reg, docsBase: deps.docsBase, ledger: deps.terminationLedger,
	}
	deps.mux.Handle("/v1/sessions/{session_id}/terminate", termChain(h))
}

func protectedAuthWrappers(deps protectedRouteDeps) routeMiddlewares {
	var mw routeMiddlewares
	if deps.limiter != nil {
		mw.rateLimit = RateLimitMiddleware(deps.limiter, deps.logger, deps.reg)
	}
	if deps.budgetCache != nil {
		mw.budget = BudgetMiddleware(deps.budgetCache, deps.logger, deps.reg)
	}
	if deps.agentVerifier != nil {
		mw.agentVerify = AgentVerificationMiddleware(deps.agentVerifier, deps.logger)
	}
	if deps.policyFetcher != nil && deps.policyVerifier != nil {
		mw.policyMutation = PolicySnapshotMiddleware(policySnapshotConfig{
			fetcher: deps.policyFetcher, verifier: deps.policyVerifier,
			class: policysnapshot.ClassMutation, metrics: deps.reg, logger: deps.logger,
		})
		mw.policyRead = PolicySnapshotMiddleware(policySnapshotConfig{
			fetcher: deps.policyFetcher, verifier: deps.policyVerifier,
			class: policysnapshot.ClassRead, metrics: deps.reg, logger: deps.logger,
		})
	}
	return mw
}

func registerAuthProbeRoutes(deps protectedRouteDeps, mw routeMiddlewares) {
	authNone := AuthMiddleware(deps.validator, deps.logger, AuthOptions{Metrics: deps.reg})
	deps.mux.Handle("/v1/internal/auth-probe", chain(authNone, mw.agentVerify, mw.policyRead, mw.rateLimit)(http.HandlerFunc(handleAuthProbe)))

	orgProbe := orgAuthProbeChain{deps: deps, mw: mw}
	deps.mux.HandleFunc("/v1/orgs/{org_id}/auth-probe", orgProbe.handler())
}

// orgAuthProbeChain bundles the shared middlewares for org-scoped auth probes.
type orgAuthProbeChain struct {
	deps protectedRouteDeps
	mw   routeMiddlewares
}

func (chainDeps orgAuthProbeChain) handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !requireMethod(w, r, http.MethodGet, chainDeps.deps.docsBase) {
			return
		}
		orgID := strings.TrimSpace(r.PathValue("org_id"))
		authOrg := AuthMiddleware(chainDeps.deps.validator, chainDeps.deps.logger,
			AuthOptions{PathOrgID: orgID, Metrics: chainDeps.deps.reg})
		chain(
			PathOrgUUIDMiddleware(chainDeps.deps.docsBase),
			authOrg,
			chainDeps.mw.agentVerify,
			chainDeps.mw.policyRead,
			chainDeps.mw.rateLimit,
		)(http.HandlerFunc(handleAuthProbe)).ServeHTTP(w, r)
	}
}

func registerChatCompletionsRoute(deps protectedRouteDeps, mw routeMiddlewares) {
	chatChain := chain(
		BodySizeLimitMiddleware(deps.cfg.MaxRequestBodyBytes, deps.docsBase),
		ContentTypeMiddleware(deps.docsBase),
		AuthMiddleware(deps.validator, deps.logger, AuthOptions{
			RequireProxyChatCompletion: true,
			Metrics:                    deps.reg,
		}),
		mw.agentVerify,
		mw.policyMutation,
		mw.rateLimit,
		mw.budget,
		DirectiveResolveMiddleware(deps.directiveResolver, deps.logger),
		ChatParseMiddleware(chatParseOpts{docsBase: deps.docsBase}),
		ProviderRoutingMiddleware(providerRoutingOpts{
			resolver:      deps.modelRouter,
			agentDefaults: deps.agentDefaults,
			log:           deps.logger,
			docsBase:      deps.docsBase,
		}),
	)
	deps.mux.Handle("/v1/chat/completions", chatChain(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handleChatCompletions(w, r, newChatCompletionHandler(deps))
	})))
}

func registerResponsesRoute(deps protectedRouteDeps, mw routeMiddlewares) {
	manifest := deps.capabilityManifest
	responsesChain := chain(
		BodySizeLimitMiddleware(deps.cfg.MaxRequestBodyBytes, deps.docsBase),
		ContentTypeMiddleware(deps.docsBase),
		AuthMiddleware(deps.validator, deps.logger, AuthOptions{RequireProxyChatCompletion: true, Metrics: deps.reg}),
		mw.agentVerify, mw.policyMutation, mw.rateLimit, mw.budget,
		ResponsesParseMiddleware(deps.docsBase),
		ProviderRoutingMiddleware(providerRoutingOpts{resolver: deps.modelRouter, agentDefaults: deps.agentDefaults, log: deps.logger, docsBase: deps.docsBase}),
		ResponsesCapabilityMiddleware(manifest, deps.docsBase),
	)
	deps.mux.Handle("/v1/responses", responsesChain(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { handleResponses(w, r, deps) })))
}

func newChatCompletionHandler(deps protectedRouteDeps) chatCompletionHandler {
	depth := deps.cfg.MaxFallbackDepth
	if depth < 1 {
		depth = 1
	}
	var pf policyFallbackChain
	if v, ok := deps.modelRouter.(policyFallbackChain); ok {
		pf = v
	}
	return chatCompletionHandler{
		log:                      deps.logger,
		docsBase:                 deps.docsBase,
		metrics:                  deps.reg,
		responsePipeline:         deps.responsePipeline,
		sessionStore:             deps.sessionStore,
		sessionCache:             deps.sessionCache,
		checkpointPool:           deps.checkpointPool,
		getOrCreateTimeout:       deps.getOrCreateTimeout,
		evidenceStore:            deps.evidenceStore,
		traceWriter:              deps.traceWriter,
		usageFactWriter:          deps.usageFactWriter,
		budgetCache:              deps.budgetCache,
		idempotencyStore:         deps.idempotencyStore,
		terminationLedger:        deps.terminationLedger,
		idempotencyTimeout:       deps.idempotencyTimeout,
		idempotencyCommitTimeout: idempotencyCASHTimeout(deps.idempotencyTimeout),
		contextClient:            deps.contextClient,
		contextEnabled:           deps.contextEnabled,
		turnBuffer:               deps.turnBuffer,
		credentialResolver:       deps.credentialResolver,
		modelRouter:              deps.modelRouter,
		policyFallback:           pf,
		maxFallbackDepth:         depth,
	}
}
