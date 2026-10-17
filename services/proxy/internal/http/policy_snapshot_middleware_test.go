package http

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/policysnapshot"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
)

var (
	policyTestKeyOnce sync.Once
	policyTestKey     *rsa.PrivateKey
)

func policyTestKeyPair(t *testing.T) *rsa.PrivateKey {
	t.Helper()
	policyTestKeyOnce.Do(func() {
		key, err := rsa.GenerateKey(rand.Reader, 2048)
		if err != nil {
			t.Error(err)
			return
		}
		policyTestKey = key
	})
	if policyTestKey == nil {
		t.Fatal("policy test key unavailable")
	}
	return policyTestKey
}

func policyPrivatePEM(t *testing.T, key *rsa.PrivateKey) string {
	t.Helper()
	return string(pem.EncodeToMemory(&pem.Block{
		Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(key),
	}))
}

func newPolicyIssuer(t *testing.T, key *rsa.PrivateKey, keyID string, epoch int64, clock func() time.Time) *policysnapshot.Issuer {
	t.Helper()
	iss, err := policysnapshot.NewIssuer(policysnapshot.IssuerConfig{
		PrivateKeyPEM: policyPrivatePEM(t, key), KeyID: keyID, Epoch: epoch, Clock: clock,
	})
	if err != nil {
		t.Fatalf("NewIssuer: %v", err)
	}
	return iss
}

func newPolicyVerifier(t *testing.T, key *rsa.PrivateKey, keyID string, minEpoch int64) *policysnapshot.Verifier {
	t.Helper()
	keys, err := policysnapshot.NewKeySet(map[string]*rsa.PublicKey{keyID: &key.PublicKey})
	if err != nil {
		t.Fatalf("NewKeySet: %v", err)
	}
	ver, err := policysnapshot.NewVerifier(policysnapshot.VerifierConfig{Keys: keys, MinEpoch: minEpoch})
	if err != nil {
		t.Fatalf("NewVerifier: %v", err)
	}
	return ver
}

func issuePolicyEnvelope(t *testing.T, iss *policysnapshot.Issuer, orgID, agentID string) policysnapshot.Envelope {
	t.Helper()
	env, err := iss.Issue(policysnapshot.IssueParams{
		OrgID: orgID, SubjectID: uuid.NewString(), AgentID: agentID, Permissions: 3,
	})
	if err != nil {
		t.Fatalf("Issue: %v", err)
	}
	return env
}

type mockPolicyFetcher struct {
	envelope *policysnapshot.Envelope
	err      error
	calls    int
	gotAgent string
}

func (m *mockPolicyFetcher) Issue(_ context.Context, _, agentID string) (*policysnapshot.Envelope, error) {
	m.calls++
	m.gotAgent = agentID
	if m.err != nil {
		return nil, m.err
	}
	return m.envelope, nil
}

type recordingPolicyMetrics struct {
	results []string
}

func (m *recordingPolicyMetrics) IncPolicySnapshot(result string) {
	m.results = append(m.results, result)
}

func (m *recordingPolicyMetrics) last() string {
	if len(m.results) == 0 {
		return ""
	}
	return m.results[len(m.results)-1]
}

type policyTerminalCapture struct {
	claims    policysnapshot.Claims
	hasClaims bool
	principal *authv1.PrincipalContext
}

// runPolicyChain runs agent verification -> policy snapshot -> terminal using a
// real agent middleware so the enriched principal context is exercised.
func runPolicyChain(
	t *testing.T,
	fetcher PolicySnapshotFetcher,
	verifier *policysnapshot.Verifier,
	class policysnapshot.Class,
) (*httptest.ResponseRecorder, *policyTerminalCapture, *recordingPolicyMetrics) {
	t.Helper()
	metrics := &recordingPolicyMetrics{}
	capture := &policyTerminalCapture{}
	policyHandler := PolicySnapshotMiddleware(policySnapshotConfig{
		fetcher: fetcher, verifier: verifier, class: class,
		metrics: metrics, logger: logger.Discard("proxy"),
	})(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			capture.claims, capture.hasClaims = PolicySnapshotClaimsFromContext(r.Context())
			if principal, ok := PrincipalContextFromContext(r.Context()); ok {
				capture.principal = principal
			}
			w.WriteHeader(http.StatusOK)
		}),
	)
	handler := AgentVerificationMiddleware(&mockAgentVerifier{}, logger.Discard("proxy"))(policyHandler)

	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req.Header.Set(validation.HeaderAgentID, agentTestAgentID())
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{
		OrgID: agentTestOrgUUID,
	}))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	return rec, capture, metrics
}

func assertPolicyCode(t *testing.T, rec *httptest.ResponseRecorder, status int, code apierror.Code) {
	t.Helper()
	if rec.Code != status {
		t.Fatalf("status = %d want %d body=%s", rec.Code, status, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), string(code)) {
		t.Fatalf("body missing %s: %s", code, rec.Body.String())
	}
}

func TestUnit_PolicySnapshot_RoundTripEnrichesPrincipal(t *testing.T) {
	t.Parallel()
	key := policyTestKeyPair(t)
	iss := newPolicyIssuer(t, key, "v1", 1, nil)
	ver := newPolicyVerifier(t, key, "v1", 1)
	env := issuePolicyEnvelope(t, iss, agentTestOrgID(), agentTestAgentID())
	fetcher := &mockPolicyFetcher{envelope: &env}

	rec, capture, metrics := runPolicyChain(t, fetcher, ver, policysnapshot.ClassMutation)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", rec.Code, rec.Body.String())
	}
	assertFetcherCall(t, fetcher)
	assertCapturedClaims(t, capture)
	assertPrincipalEnriched(t, capture)
	if metrics.last() != policysnapshot.MetricIssued {
		t.Fatalf("metric = %q want issued", metrics.last())
	}
}

func assertFetcherCall(t *testing.T, fetcher *mockPolicyFetcher) {
	t.Helper()
	if fetcher.calls != 1 || fetcher.gotAgent != agentTestAgentID() {
		t.Fatalf("fetcher calls=%d agent=%q", fetcher.calls, fetcher.gotAgent)
	}
}

func assertCapturedClaims(t *testing.T, capture *policyTerminalCapture) {
	t.Helper()
	if !capture.hasClaims {
		t.Fatal("claims missing from context")
	}
	if capture.claims.OrgID != agentTestOrgID() || capture.claims.AgentID != agentTestAgentID() {
		t.Fatalf("claims = %+v", capture.claims)
	}
}

func assertPrincipalEnriched(t *testing.T, capture *policyTerminalCapture) {
	t.Helper()
	if capture.principal == nil {
		t.Fatalf("principal missing, claims=%+v", capture.claims)
	}
	if capture.principal.GetAuthzSnapshotId() != capture.claims.SnapshotID {
		t.Fatalf("principal snapshot id = %q want %q", capture.principal.GetAuthzSnapshotId(), capture.claims.SnapshotID)
	}
	if capture.principal.GetAuthzSnapshotDigest() != capture.claims.Digest {
		t.Fatalf("principal snapshot digest = %q want %q", capture.principal.GetAuthzSnapshotDigest(), capture.claims.Digest)
	}
}

func TestUnit_PolicySnapshot_IssueFailures(t *testing.T) {
	t.Parallel()
	key := policyTestKeyPair(t)
	ver := newPolicyVerifier(t, key, "v1", 1)

	cases := []struct {
		name       string
		err        error
		wantStatus int
		wantCode   apierror.Code
		wantMetric string
	}{
		{"invalid token", auth.ErrInvalidToken, http.StatusUnauthorized, apierror.CodeInvalidToken, policysnapshot.MetricInvalidToken},
		{"denied", auth.ErrPolicySnapshotDenied, http.StatusForbidden, apierror.CodeAgentNotAuthorized, policysnapshot.MetricDenied},
		{"unavailable", auth.ErrPolicySnapshotUnavailable, http.StatusServiceUnavailable, apierror.CodeSnapshotUnavailable, policysnapshot.MetricUnavailable},
		{"unknown error", errors.New("boom"), http.StatusServiceUnavailable, apierror.CodeSnapshotUnavailable, policysnapshot.MetricUnavailable},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			rec, _, metrics := runPolicyChain(t, &mockPolicyFetcher{err: tc.err}, ver, policysnapshot.ClassMutation)
			assertPolicyCode(t, rec, tc.wantStatus, tc.wantCode)
			if metrics.last() != tc.wantMetric {
				t.Fatalf("metric = %q want %q", metrics.last(), tc.wantMetric)
			}
		})
	}
}

func TestUnit_PolicySnapshot_VerifyFailures(t *testing.T) {
	t.Parallel()
	key := policyTestKeyPair(t)
	now := time.Now().UTC()
	staleIss := newPolicyIssuer(t, key, "v1", 1, func() time.Time { return now.Add(-2 * time.Minute) })
	otherOrgIss := newPolicyIssuer(t, key, "v1", 1, nil)

	validEnv := issuePolicyEnvelope(t, newPolicyIssuer(t, key, "v1", 1, nil), agentTestOrgID(), agentTestAgentID())
	tamperedSig := validEnv
	tamperedSig.Signature = append([]byte(nil), validEnv.Signature...)
	tamperedSig.Signature[0] ^= 0xFF
	unknownKey := validEnv
	unknownKey.KeyID = "rotated-out"

	cases := []struct {
		name       string
		envelope   policysnapshot.Envelope
		wantStatus int
		wantCode   apierror.Code
		wantMetric string
	}{
		{
			name:       "expired",
			envelope:   issuePolicyEnvelope(t, staleIss, agentTestOrgID(), agentTestAgentID()),
			wantStatus: http.StatusForbidden, wantCode: apierror.CodeSnapshotExpired, wantMetric: policysnapshot.MetricExpired,
		},
		{
			name:       "org mismatch",
			envelope:   issuePolicyEnvelope(t, otherOrgIss, uuid.NewString(), agentTestAgentID()),
			wantStatus: http.StatusForbidden, wantCode: apierror.CodeSnapshotOrgMismatch, wantMetric: policysnapshot.MetricOrgMismatch,
		},
		{
			name:       "agent mismatch",
			envelope:   issuePolicyEnvelope(t, otherOrgIss, agentTestOrgID(), uuid.NewString()),
			wantStatus: http.StatusForbidden, wantCode: apierror.CodeSnapshotAgentMismatch, wantMetric: policysnapshot.MetricAgentMismatch,
		},
		{
			name:       "unknown key",
			envelope:   unknownKey,
			wantStatus: http.StatusForbidden, wantCode: apierror.CodeSnapshotKeyUnknown, wantMetric: policysnapshot.MetricKeyUnknown,
		},
		{
			name:       "tampered signature",
			envelope:   tamperedSig,
			wantStatus: http.StatusForbidden, wantCode: apierror.CodeSnapshotSignatureInvalid, wantMetric: policysnapshot.MetricSignatureInvalid,
		},
		{
			name:       "malformed payload",
			envelope:   policysnapshot.Envelope{Algorithm: policysnapshot.AlgorithmRS256, KeyID: "v1", Payload: []byte("{"), Signature: []byte("sig")},
			wantStatus: http.StatusForbidden, wantCode: apierror.CodeSnapshotSignatureInvalid, wantMetric: policysnapshot.MetricSignatureInvalid,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			env := tc.envelope
			rec, _, metrics := runPolicyChain(t, &mockPolicyFetcher{envelope: &env}, newPolicyVerifier(t, key, "v1", 1), policysnapshot.ClassMutation)
			assertPolicyCode(t, rec, tc.wantStatus, tc.wantCode)
			if metrics.last() != tc.wantMetric {
				t.Fatalf("metric = %q want %q", metrics.last(), tc.wantMetric)
			}
		})
	}
}

func TestUnit_PolicySnapshot_FailsClosedWhenUnconfigured(t *testing.T) {
	t.Parallel()
	rec, _, metrics := runPolicyChain(t, nil, nil, policysnapshot.ClassMutation)
	assertPolicyCode(t, rec, http.StatusServiceUnavailable, apierror.CodeSnapshotUnavailable)
	if metrics.last() != policysnapshot.MetricUnavailable {
		t.Fatalf("metric = %q", metrics.last())
	}
}

func TestUnit_PolicySnapshot_ReadClassRejectsMutationAge(t *testing.T) {
	t.Parallel()
	key := policyTestKeyPair(t)
	iss := newPolicyIssuer(t, key, "v1", 1, func() time.Time { return time.Now().UTC().Add(-45 * time.Second) })
	env := issuePolicyEnvelope(t, iss, agentTestOrgID(), agentTestAgentID())

	mutationRec, _, _ := runPolicyChain(t, &mockPolicyFetcher{envelope: &env}, newPolicyVerifier(t, key, "v1", 1), policysnapshot.ClassMutation)
	assertPolicyCode(t, mutationRec, http.StatusForbidden, apierror.CodeSnapshotExpired)

	readRec, _, _ := runPolicyChain(t, &mockPolicyFetcher{envelope: &env}, newPolicyVerifier(t, key, "v1", 1), policysnapshot.ClassRead)
	if readRec.Code != http.StatusOK {
		t.Fatalf("read class status = %d body=%s", readRec.Code, readRec.Body.String())
	}
}

func TestUnit_PolicySnapshot_MissingContextsFailClosed(t *testing.T) {
	t.Parallel()
	key := policyTestKeyPair(t)
	handler := PolicySnapshotMiddleware(policySnapshotConfig{
		fetcher: &mockPolicyFetcher{}, verifier: newPolicyVerifier(t, key, "v1", 1),
		class: policysnapshot.ClassMutation, logger: logger.Discard("proxy"),
	})(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) }),
	)

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil))
	assertPolicyCode(t, rec, http.StatusInternalServerError, apierror.CodeServiceDegraded)

	agentCtx := WithAgent(context.Background(), auth.AgentRecord{ID: uuid.MustParse(agentTestAgentID()), OrgID: agentTestOrgUUID})
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil).WithContext(agentCtx)
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	assertPolicyCode(t, rec, http.StatusInternalServerError, apierror.CodeServiceDegraded)

	authCtx := auth.WithContext(context.Background(), &auth.ValidateResult{OrgID: agentTestOrgUUID})
	req = httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil).WithContext(authCtx)
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	assertPolicyCode(t, rec, http.StatusInternalServerError, apierror.CodeServiceDegraded)
}

func TestUnit_PolicySnapshot_InvalidAuthorizationHeader(t *testing.T) {
	t.Parallel()
	key := policyTestKeyPair(t)
	handler := PolicySnapshotMiddleware(policySnapshotConfig{
		fetcher: &mockPolicyFetcher{}, verifier: newPolicyVerifier(t, key, "v1", 1),
		class: policysnapshot.ClassMutation, metrics: &recordingPolicyMetrics{},
		logger: logger.Discard("proxy"),
	})(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) }),
	)
	agentCtx := WithAgent(context.Background(), auth.AgentRecord{ID: uuid.MustParse(agentTestAgentID()), OrgID: agentTestOrgUUID})
	ctx := auth.WithContext(agentCtx, &auth.ValidateResult{OrgID: agentTestOrgUUID})

	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil).WithContext(ctx)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	assertPolicyCode(t, rec, http.StatusUnauthorized, apierror.CodeInvalidToken)
}

func TestUnit_PolicySnapshot_NilEnvelopeFailsClosed(t *testing.T) {
	t.Parallel()
	key := policyTestKeyPair(t)
	rec, _, metrics := runPolicyChain(t, &mockPolicyFetcher{}, newPolicyVerifier(t, key, "v1", 1), policysnapshot.ClassMutation)
	assertPolicyCode(t, rec, http.StatusServiceUnavailable, apierror.CodeSnapshotUnavailable)
	if metrics.last() != policysnapshot.MetricUnavailable {
		t.Fatalf("metric = %q want unavailable", metrics.last())
	}
}

func TestUnit_PolicySnapshot_SucceedsWithoutPrincipalContext(t *testing.T) {
	t.Parallel()
	key := policyTestKeyPair(t)
	iss := newPolicyIssuer(t, key, "v1", 1, nil)
	ver := newPolicyVerifier(t, key, "v1", 1)
	env := issuePolicyEnvelope(t, iss, agentTestOrgID(), agentTestAgentID())

	metrics := &recordingPolicyMetrics{}
	handler := PolicySnapshotMiddleware(policySnapshotConfig{
		fetcher: &mockPolicyFetcher{envelope: &env}, verifier: ver,
		class: policysnapshot.ClassMutation, metrics: metrics, logger: logger.Discard("proxy"),
	})(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if _, ok := PrincipalContextFromContext(r.Context()); ok {
				t.Error("principal context unexpectedly present")
			}
			if _, ok := PolicySnapshotClaimsFromContext(r.Context()); !ok {
				t.Error("claims missing from context")
			}
			w.WriteHeader(http.StatusOK)
		}),
	)
	agentCtx := WithAgent(context.Background(), auth.AgentRecord{ID: uuid.MustParse(agentTestAgentID()), OrgID: agentTestOrgUUID})
	ctx := auth.WithContext(agentCtx, &auth.ValidateResult{OrgID: agentTestOrgUUID})
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req = req.WithContext(ctx)

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", rec.Code, rec.Body.String())
	}
	if metrics.last() != policysnapshot.MetricIssued {
		t.Fatalf("metric = %q want issued", metrics.last())
	}
}
