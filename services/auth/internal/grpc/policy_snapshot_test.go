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

func TestIssuePolicySnapshotHappyPath(t *testing.T) {
	srv := newTestServer(t, &fakeTokenValidator{}, nil, nil)
	issuer := &fakePolicyIssuer{}
	srv.policyIssuer = issuer
	orgID := uuid.NewString()
	agentID := uuid.NewString()
	userID := uuid.NewString()

	resp, err := srv.IssuePolicySnapshot(policyCallerCtx(CallerContext{
		OrgID: orgID, TokenID: uuid.NewString(), UserID: userID, Permissions: 42,
	}), &authv1.IssuePolicySnapshotRequest{AgentId: agentID})
	if err != nil {
		t.Fatalf("IssuePolicySnapshot: %v", err)
	}
	if issuer.calls != 1 {
		t.Fatalf("issuer calls = %d, want 1", issuer.calls)
	}
	if issuer.got.OrgID != orgID || issuer.got.AgentID != agentID || issuer.got.SubjectID != userID {
		t.Fatalf("issue params = %+v", issuer.got)
	}
	if issuer.got.Permissions != 42 {
		t.Fatalf("permissions = %d, want 42", issuer.got.Permissions)
	}
	env := resp.GetEnvelope()
	if env.GetAlgorithm() != policysnapshot.AlgorithmRS256 || env.GetKeyId() != "v1" {
		t.Fatalf("envelope = %+v", env)
	}
	if string(env.GetPayload()) != "payload" || string(env.GetSignature()) != "signature" {
		t.Fatalf("envelope payload/signature = %q/%q", env.GetPayload(), env.GetSignature())
	}
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
			srv := newTestServer(t, &fakeTokenValidator{}, nil, nil)
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
	srv := newTestServer(t, &fakeTokenValidator{}, nil, nil)
	srv.policyIssuer = issuer
	orgID := uuid.NewString()
	agentID := uuid.NewString()
	userID := uuid.NewString()

	resp, err := srv.IssuePolicySnapshot(policyCallerCtx(CallerContext{
		OrgID: orgID, TokenID: uuid.NewString(), UserID: userID, Permissions: 7,
	}), &authv1.IssuePolicySnapshotRequest{AgentId: agentID})
	if err != nil {
		t.Fatalf("IssuePolicySnapshot: %v", err)
	}
	verifier, err := policysnapshot.NewVerifier(policysnapshot.VerifierConfig{
		Keys:     policyKeySet(t, key),
		MinEpoch: 4,
		Clock:    func() time.Time { return time.Date(2026, 10, 17, 12, 0, 10, 0, time.UTC) },
	})
	if err != nil {
		t.Fatal(err)
	}
	env := resp.GetEnvelope()
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
	if claims.OrgID != orgID || claims.AgentID != agentID || claims.SubjectID != userID || claims.Permissions != 7 {
		t.Fatalf("claims = %+v", claims)
	}
	if claims.Epoch != 4 {
		t.Fatalf("epoch = %d, want 4", claims.Epoch)
	}
}

func policyKeySet(t *testing.T, key *rsa.PrivateKey) policysnapshot.KeySet {
	t.Helper()
	set, err := policysnapshot.NewKeySet(map[string]*rsa.PublicKey{"v1": &key.PublicKey})
	if err != nil {
		t.Fatal(err)
	}
	return set
}
