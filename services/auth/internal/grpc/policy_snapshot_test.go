package grpcserver

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/policysnapshot"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
)

type fakePolicyIssuer struct {
	envelope policysnapshot.Envelope
	err      error
	calls    int
	got      policysnapshot.IssueParams
}

func (f *fakePolicyIssuer) Issue(p policysnapshot.IssueParams) (policysnapshot.Envelope, error) {
	f.calls++
	f.got = p
	if f.err != nil {
		return policysnapshot.Envelope{}, f.err
	}
	if f.envelope.Payload == nil {
		return policysnapshot.Envelope{
			Algorithm: policysnapshot.AlgorithmRS256, KeyID: "v1",
			Payload: []byte("payload"), Signature: []byte("signature"),
		}, nil
	}
	return f.envelope, nil
}

func policyCallerCtx(caller CallerContext) context.Context {
	return ContextWithCaller(context.Background(), caller)
}

type issueExpectations struct {
	orgID       string
	agentID     string
	subjectID   string
	permissions int64
}

func assertIssueParams(t *testing.T, issuer *fakePolicyIssuer, want issueExpectations) {
	t.Helper()
	if issuer.calls != 1 {
		t.Fatalf("issuer calls = %d, want 1", issuer.calls)
	}
	got := issuer.got
	if got.OrgID != want.orgID {
		t.Fatalf("org = %q, want %q", got.OrgID, want.orgID)
	}
	if got.AgentID != want.agentID {
		t.Fatalf("agent = %q, want %q", got.AgentID, want.agentID)
	}
	if got.SubjectID != want.subjectID {
		t.Fatalf("subject = %q, want %q", got.SubjectID, want.subjectID)
	}
	if got.Permissions != want.permissions {
		t.Fatalf("permissions = %d, want %d", got.Permissions, want.permissions)
	}
}

func assertVerifiedClaims(t *testing.T, claims policysnapshot.Claims, want issueExpectations) {
	t.Helper()
	if claims.OrgID != want.orgID {
		t.Fatalf("claims org = %q, want %q", claims.OrgID, want.orgID)
	}
	if claims.AgentID != want.agentID {
		t.Fatalf("claims agent = %q, want %q", claims.AgentID, want.agentID)
	}
	if claims.SubjectID != want.subjectID {
		t.Fatalf("claims subject = %q, want %q", claims.SubjectID, want.subjectID)
	}
	if claims.Permissions != want.permissions {
		t.Fatalf("claims permissions = %d, want %d", claims.Permissions, want.permissions)
	}
}

func assertIssuedEnvelope(t *testing.T, env *authv1.PolicySnapshotEnvelope) {
	t.Helper()
	if env.GetAlgorithm() != policysnapshot.AlgorithmRS256 || env.GetKeyId() != "v1" {
		t.Fatalf("envelope = %+v", env)
	}
	if string(env.GetPayload()) != "payload" || string(env.GetSignature()) != "signature" {
		t.Fatalf("envelope payload/signature = %q/%q", env.GetPayload(), env.GetSignature())
	}
}

func TestIssuePolicySnapshotHappyPath(t *testing.T) {
	orgID := uuid.NewString()
	agentID := uuid.NewString()
	userID := uuid.NewString()
	srv := newTestServer(t, &fakeTokenValidator{}, nil,
		&fakeAgentAPI{view: service.AgentView{ID: agentID, OrgID: orgID, Status: "active"}})
	issuer := &fakePolicyIssuer{}
	srv.policyIssuer = issuer

	resp, err := srv.IssuePolicySnapshot(policyCallerCtx(CallerContext{
		OrgID: orgID, TokenID: uuid.NewString(), UserID: userID, Permissions: 42,
	}), &authv1.IssuePolicySnapshotRequest{AgentId: agentID})
	if err != nil {
		t.Fatalf("IssuePolicySnapshot: %v", err)
	}
	assertIssueParams(t, issuer, issueExpectations{orgID: orgID, agentID: agentID, subjectID: userID, permissions: 42})
	assertIssuedEnvelope(t, resp.GetEnvelope())
}

func TestIssuePolicySnapshotSubjectFallback(t *testing.T) {
	srv := newTestServer(t, &fakeTokenValidator{}, nil, nil)
	issuer := &fakePolicyIssuer{}
	srv.policyIssuer = issuer
	tokenID := uuid.NewString()

	if _, err := srv.IssuePolicySnapshot(policyCallerCtx(CallerContext{
		OrgID: uuid.NewString(), TokenID: tokenID, Permissions: 1,
	}), &authv1.IssuePolicySnapshotRequest{}); err != nil {
		t.Fatalf("IssuePolicySnapshot: %v", err)
	}
	if issuer.got.SubjectID != tokenID {
		t.Fatalf("subject = %q, want token id %q", issuer.got.SubjectID, tokenID)
	}
	if issuer.got.AgentID != "" {
		t.Fatalf("agent = %q, want empty", issuer.got.AgentID)
	}
}

func TestIssuePolicySnapshotAgentBinding(t *testing.T) {
	boundAgent := uuid.NewString()
	cases := []struct {
		name    string
		caller  CallerContext
		request string
		want    codes.Code
	}{
		{
			name: "agent-scoped match", caller: CallerContext{OrgID: uuid.NewString(), TokenID: uuid.NewString(), AgentID: boundAgent},
			request: boundAgent, want: codes.OK,
		},
		{
			name: "agent-scoped mismatch", caller: CallerContext{OrgID: uuid.NewString(), TokenID: uuid.NewString(), AgentID: boundAgent},
			request: uuid.NewString(), want: codes.PermissionDenied,
		},
		{
			name: "agent-scoped empty request", caller: CallerContext{OrgID: uuid.NewString(), TokenID: uuid.NewString(), AgentID: boundAgent},
			request: "", want: codes.InvalidArgument,
		},
		{
			name: "org-scoped invalid agent", caller: CallerContext{OrgID: uuid.NewString(), TokenID: uuid.NewString()},
			request: "not-a-uuid", want: codes.InvalidArgument,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			srv := newTestServer(t, &fakeTokenValidator{}, nil,
				&fakeAgentAPI{view: service.AgentView{ID: boundAgent}})
			issuer := &fakePolicyIssuer{}
			srv.policyIssuer = issuer
			_, err := srv.IssuePolicySnapshot(policyCallerCtx(tc.caller), &authv1.IssuePolicySnapshotRequest{AgentId: tc.request})
			assertGRPCCode(t, err, tc.want)
			if tc.want != codes.OK && issuer.calls != 0 {
				t.Fatalf("issuer called %d times on denial", issuer.calls)
			}
		})
	}
}

func TestIssuePolicySnapshotAgentValidation(t *testing.T) {
	orgID := uuid.NewString()
	agentID := uuid.NewString()
	cases := []struct {
		name      string
		caller    CallerContext
		agents    *fakeAgentAPI
		request   string
		want      codes.Code
		wantIssue bool
	}{
		{
			name:   "authorized agent",
			caller: CallerContext{OrgID: orgID, TokenID: uuid.NewString()},
			agents: &fakeAgentAPI{view: service.AgentView{ID: agentID, OrgID: orgID, Status: "active"}},
			want:   codes.OK, wantIssue: true,
		},
		{
			name:   "agent not authorized",
			caller: CallerContext{OrgID: orgID, TokenID: uuid.NewString()},
			agents: &fakeAgentAPI{},
			want:   codes.PermissionDenied,
		},
		{
			name:   "agent inactive",
			caller: CallerContext{OrgID: orgID, TokenID: uuid.NewString()},
			agents: &fakeAgentAPI{err: service.ErrAgentInactive},
			want:   codes.PermissionDenied,
		},
		{
			name:   "agent lookup failure",
			caller: CallerContext{OrgID: orgID, TokenID: uuid.NewString()},
			agents: &fakeAgentAPI{err: errors.New("db down")},
			want:   codes.Internal,
		},
		{
			name:   "agent lookup canceled",
			caller: CallerContext{OrgID: orgID, TokenID: uuid.NewString()},
			agents: &fakeAgentAPI{err: context.Canceled},
			want:   codes.Canceled,
		},
		{
			name:   "agent lookup deadline exceeded",
			caller: CallerContext{OrgID: orgID, TokenID: uuid.NewString()},
			agents: &fakeAgentAPI{err: context.DeadlineExceeded},
			want:   codes.DeadlineExceeded,
		},
		{
			name:   "caller org not a uuid",
			caller: CallerContext{OrgID: "not-a-uuid", TokenID: uuid.NewString()},
			agents: &fakeAgentAPI{view: service.AgentView{ID: agentID}},
			want:   codes.Internal,
		},
		{
			name:    "caller agent binding not a uuid",
			caller:  CallerContext{OrgID: orgID, TokenID: uuid.NewString(), AgentID: "not-a-uuid"},
			agents:  &fakeAgentAPI{view: service.AgentView{ID: agentID}},
			request: "not-a-uuid",
			want:    codes.Internal,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			request := tc.request
			if request == "" {
				request = agentID
			}
			srv := newTestServer(t, &fakeTokenValidator{}, nil, tc.agents)
			issuer := &fakePolicyIssuer{}
			srv.policyIssuer = issuer
			_, err := srv.IssuePolicySnapshot(policyCallerCtx(tc.caller), &authv1.IssuePolicySnapshotRequest{AgentId: request})
			assertGRPCCode(t, err, tc.want)
			if tc.wantIssue && issuer.calls != 1 {
				t.Fatalf("issuer calls = %d, want 1", issuer.calls)
			}
			if !tc.wantIssue && issuer.calls != 0 {
				t.Fatalf("issuer called %d times on denial", issuer.calls)
			}
		})
	}
}

func TestIssuePolicySnapshotFailures(t *testing.T) {
	cases := []struct {
		name      string
		caller    *CallerContext
		issuer    *fakePolicyIssuer
		nilIssuer bool
		want      codes.Code
	}{
		{name: "missing caller", want: codes.Unauthenticated, issuer: &fakePolicyIssuer{}},
		{name: "empty org", caller: &CallerContext{TokenID: uuid.NewString()}, want: codes.Internal, issuer: &fakePolicyIssuer{}},
		{
			name:   "missing subject",
			caller: &CallerContext{OrgID: uuid.NewString()},
			want:   codes.Internal, issuer: &fakePolicyIssuer{},
		},
		{
			name:   "issuer unavailable",
			caller: &CallerContext{OrgID: uuid.NewString(), TokenID: uuid.NewString()},
			want:   codes.FailedPrecondition, nilIssuer: true,
		},
		{
			name:   "issuer failure",
			caller: &CallerContext{OrgID: uuid.NewString(), TokenID: uuid.NewString()},
			want:   codes.Internal, issuer: &fakePolicyIssuer{err: errors.New("sign failure")},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			srv := newTestServer(t, &fakeTokenValidator{}, nil, nil)
			if !tc.nilIssuer {
				srv.policyIssuer = tc.issuer
			}
			ctx := context.Background()
			if tc.caller != nil {
				ctx = policyCallerCtx(*tc.caller)
			}
			_, err := srv.IssuePolicySnapshot(ctx, &authv1.IssuePolicySnapshotRequest{})
			assertGRPCCode(t, err, tc.want)
		})
	}
}

func TestIssuePolicySnapshotEnvelopeVerifies(t *testing.T) {
	key, issuer := newPolicyTestIssuer(t)
	orgID := uuid.NewString()
	agentID := uuid.NewString()
	userID := uuid.NewString()
	srv := newTestServer(t, &fakeTokenValidator{}, nil,
		&fakeAgentAPI{view: service.AgentView{ID: agentID, OrgID: orgID, Status: "active"}})
	srv.policyIssuer = issuer

	env := issueSnapshotEnvelope(t, srv, CallerContext{
		OrgID: orgID, TokenID: uuid.NewString(), UserID: userID, Permissions: 7,
	}, agentID)
	claims := verifyIssuedEnvelope(t, key, env, orgID, agentID)

	assertVerifiedClaims(t, claims, issueExpectations{orgID: orgID, agentID: agentID, subjectID: userID, permissions: 7})
	if claims.Epoch != 4 {
		t.Fatalf("epoch = %d, want 4", claims.Epoch)
	}
}

func newPolicyTestIssuer(t *testing.T) (*rsa.PrivateKey, *policysnapshot.Issuer) {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	privPEM := string(pem.EncodeToMemory(&pem.Block{
		Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(key),
	}))
	issuer, err := policysnapshot.NewIssuer(policysnapshot.IssuerConfig{
		PrivateKeyPEM: privPEM, KeyID: "v1", Epoch: 4,
		Clock: func() time.Time { return time.Date(2026, 10, 17, 12, 0, 0, 0, time.UTC) },
	})
	if err != nil {
		t.Fatal(err)
	}
	return key, issuer
}

func issueSnapshotEnvelope(t *testing.T, srv *Server, caller CallerContext, agentID string) *authv1.PolicySnapshotEnvelope {
	t.Helper()
	resp, err := srv.IssuePolicySnapshot(policyCallerCtx(caller), &authv1.IssuePolicySnapshotRequest{AgentId: agentID})
	if err != nil {
		t.Fatalf("IssuePolicySnapshot: %v", err)
	}
	return resp.GetEnvelope()
}

func verifyIssuedEnvelope(t *testing.T, key *rsa.PrivateKey, env *authv1.PolicySnapshotEnvelope, orgID, agentID string) policysnapshot.Claims {
	t.Helper()
	verifier, err := policysnapshot.NewVerifier(policysnapshot.VerifierConfig{
		Keys:     policyKeySet(t, key),
		MinEpoch: 4,
		Clock:    func() time.Time { return time.Date(2026, 10, 17, 12, 0, 10, 0, time.UTC) },
	})
	if err != nil {
		t.Fatal(err)
	}
	claims, err := verifier.Verify(policysnapshot.VerifyParams{
		Envelope: policysnapshot.Envelope{
			Algorithm: env.GetAlgorithm(), KeyID: env.GetKeyId(),
			Payload: env.GetPayload(), Signature: env.GetSignature(),
		},
		ExpectedOrgID: orgID, ExpectedAgentID: agentID, Class: policysnapshot.ClassMutation,
	})
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	return claims
}

func policyKeySet(t *testing.T, key *rsa.PrivateKey) policysnapshot.KeySet {
	t.Helper()
	set, err := policysnapshot.NewKeySet(map[string]*rsa.PublicKey{"v1": &key.PublicKey})
	if err != nil {
		t.Fatal(err)
	}
	return set
}
