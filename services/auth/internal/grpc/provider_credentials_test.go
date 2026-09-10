package grpcserver

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
)

type fakeCredAPI struct {
	createFn func(context.Context, service.CreateInput) (service.ProviderCredentialMetadata, error)
	getFn    func(context.Context, service.OrgProviderRef) (service.GetProviderCredentialResult, error)
	listFn   func(context.Context, string) ([]service.ProviderCredentialMetadata, error)
	deleteFn func(context.Context, service.OrgProviderRef) error
}

func (f *fakeCredAPI) Create(ctx context.Context, in service.CreateInput) (service.ProviderCredentialMetadata, error) {
	if f.createFn != nil {
		return f.createFn(ctx, in)
	}
	return service.ProviderCredentialMetadata{}, nil
}

func (f *fakeCredAPI) Get(ctx context.Context, ref service.OrgProviderRef) (service.GetProviderCredentialResult, error) {
	if f.getFn != nil {
		return f.getFn(ctx, ref)
	}
	return service.GetProviderCredentialResult{}, nil
}

func (f *fakeCredAPI) List(ctx context.Context, orgID string) ([]service.ProviderCredentialMetadata, error) {
	if f.listFn != nil {
		return f.listFn(ctx, orgID)
	}
	return nil, nil
}

func (f *fakeCredAPI) Delete(ctx context.Context, ref service.OrgProviderRef) error {
	if f.deleteFn != nil {
		return f.deleteFn(ctx, ref)
	}
	return nil
}

func newCredServer(t testing.TB, cred providerCredentialAPI) *Server {
	t.Helper()
	srv, err := NewServer(ServerDeps{
		Validator: &fakeTokenValidator{fn: func(context.Context, string) (*authv1.ValidateTokenResponse, error) {
			return nil, errors.New("unused")
		}},
		TokenService: &fakeTokenAPI{},
		AgentService: &fakeAgentAPI{},
		CredService:  cred,
		Metrics:      testAuthRegistry(),
		Log:          logger.Discard("auth"),
	})
	if err != nil {
		t.Fatalf("NewServer: %v", err)
	}
	return srv
}

func settingsWriteCtx(orgID string) context.Context {
	return ContextWithCaller(context.Background(), CallerContext{
		OrgID: orgID, TokenID: uuid.NewString(), UserID: uuid.NewString(),
		Permissions: permissions.OrgSettingsWrite,
	})
}

func TestUnit_ProviderCredentialRPCs_NilService(t *testing.T) {
	t.Parallel()
	srv := newTestServer(t, &fakeTokenValidator{fn: func(context.Context, string) (*authv1.ValidateTokenResponse, error) {
		return nil, errors.New("unused")
	}}, nil, nil)
	org := uuid.NewString()
	ctx := settingsWriteCtx(org)

	_, err := srv.CreateProviderCredential(ctx, &authv1.CreateProviderCredentialRequest{
		OrgId: org, ProviderName: "openai", ApiKey: "sk-test",
	})
	assertGRPCCode(t, err, codes.FailedPrecondition)

	_, err = srv.GetProviderCredential(ctx, &authv1.GetProviderCredentialRequest{
		OrgId: org, ProviderName: "openai",
	})
	assertGRPCCode(t, err, codes.FailedPrecondition)

	_, err = srv.ListProviderCredentials(ctx, &authv1.ListProviderCredentialsRequest{OrgId: org})
	assertGRPCCode(t, err, codes.FailedPrecondition)

	_, err = srv.DeleteProviderCredential(ctx, &authv1.DeleteProviderCredentialRequest{
		OrgId: org, ProviderName: "openai",
	})
	assertGRPCCode(t, err, codes.FailedPrecondition)
}

func TestUnit_CreateProviderCredential_HappyPath(t *testing.T) {
	t.Parallel()
	org := uuid.NewString()
	validated := time.Now().UTC().Truncate(time.Second)
	fake := &fakeCredAPI{createFn: happyCreateFn(t, org, validated)}
	resp, err := newCredServer(t, fake).CreateProviderCredential(settingsWriteCtx(org), &authv1.CreateProviderCredentialRequest{
		OrgId: org, ProviderName: "openai", ApiKey: "sk-live", BaseUrl: "https://example.com",
	})
	if err != nil {
		t.Fatal(err)
	}
	assertCreateCredResponse(t, resp, validated)
}

func happyCreateFn(t *testing.T, org string, validated time.Time) func(context.Context, service.CreateInput) (service.ProviderCredentialMetadata, error) {
	t.Helper()
	return func(_ context.Context, in service.CreateInput) (service.ProviderCredentialMetadata, error) {
		if in.OrgID != org || in.ProviderName != "openai" || in.APIKey != "sk-live" {
			t.Fatalf("input=%+v", in)
		}
		return service.ProviderCredentialMetadata{
			ProviderName: "openai", Status: "active", KeyHint: "live",
			BaseURL: in.BaseURL, EncryptionKeyID: "v1", LastValidatedAt: &validated,
		}, nil
	}
}

func assertCreateCredResponse(t *testing.T, resp *authv1.CreateProviderCredentialResponse, validated time.Time) {
	t.Helper()
	if resp.GetProviderName() != "openai" {
		t.Fatalf("provider=%q", resp.GetProviderName())
	}
	if resp.GetKeyHint() != "live" {
		t.Fatalf("hint=%q", resp.GetKeyHint())
	}
	if resp.GetBaseUrl() != "https://example.com" {
		t.Fatalf("base=%q", resp.GetBaseUrl())
	}
	if resp.GetLastValidatedAt() == nil || !resp.GetLastValidatedAt().AsTime().Equal(validated) {
		t.Fatalf("last_validated_at=%v", resp.GetLastValidatedAt())
	}
}

func TestUnit_CreateProviderCredential_AuthzAndMappedErrors(t *testing.T) {
	t.Parallel()
	org := uuid.NewString()
	cases := []struct {
		name     string
		ctx      context.Context
		createFn func(context.Context, service.CreateInput) (service.ProviderCredentialMetadata, error)
		want     codes.Code
	}{
		{
			name: "unauthenticated",
			ctx:  context.Background(),
			want: codes.Unauthenticated,
		},
		{
			name: "wrong_org",
			ctx: ContextWithCaller(context.Background(), CallerContext{
				OrgID: uuid.NewString(), Permissions: permissions.Admin,
			}),
			want: codes.PermissionDenied,
		},
		{
			name: "missing_permission",
			ctx: ContextWithCaller(context.Background(), CallerContext{
				OrgID: org, Permissions: permissions.ReadOnly,
			}),
			want: codes.PermissionDenied,
		},
		{
			name: "invalid_provider",
			ctx:  settingsWriteCtx(org),
			createFn: func(context.Context, service.CreateInput) (service.ProviderCredentialMetadata, error) {
				return service.ProviderCredentialMetadata{}, service.ErrInvalidProviderName
			},
			want: codes.InvalidArgument,
		},
		{
			name: "empty_key",
			ctx:  settingsWriteCtx(org),
			createFn: func(context.Context, service.CreateInput) (service.ProviderCredentialMetadata, error) {
				return service.ProviderCredentialMetadata{}, service.ErrEmptyAPIKey
			},
			want: codes.InvalidArgument,
		},
		{
			name: "master_missing",
			ctx:  settingsWriteCtx(org),
			createFn: func(context.Context, service.CreateInput) (service.ProviderCredentialMetadata, error) {
				return service.ProviderCredentialMetadata{}, service.ErrCredentialsMasterKeyMissing
			},
			want: codes.FailedPrecondition,
		},
		{
			name: "internal",
			ctx:  settingsWriteCtx(org),
			createFn: func(context.Context, service.CreateInput) (service.ProviderCredentialMetadata, error) {
				return service.ProviderCredentialMetadata{}, errors.New("db down")
			},
			want: codes.Internal,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			_, err := newCredServer(t, &fakeCredAPI{createFn: tc.createFn}).CreateProviderCredential(
				tc.ctx,
				&authv1.CreateProviderCredentialRequest{OrgId: org, ProviderName: "openai", ApiKey: "sk"},
			)
			assertGRPCCode(t, err, tc.want)
		})
	}
}

func TestUnit_GetProviderCredential_Paths(t *testing.T) {
	t.Parallel()
	org := uuid.NewString()
	fake := &fakeCredAPI{
		getFn: func(_ context.Context, ref service.OrgProviderRef) (service.GetProviderCredentialResult, error) {
			if ref.OrgID != org || ref.ProviderName != "anthropic" {
				t.Fatalf("ref=%+v", ref)
			}
			return service.GetProviderCredentialResult{
				APIKey: "sk-ant", BaseURL: "https://byo.example",
			}, nil
		},
	}
	srv := newCredServer(t, fake)

	_, err := srv.GetProviderCredential(context.Background(), &authv1.GetProviderCredentialRequest{
		OrgId: org, ProviderName: "anthropic",
	})
	assertGRPCCode(t, err, codes.Unauthenticated)

	_, err = srv.GetProviderCredential(settingsWriteCtx(uuid.NewString()), &authv1.GetProviderCredentialRequest{
		OrgId: org, ProviderName: "anthropic",
	})
	assertGRPCCode(t, err, codes.PermissionDenied)

	resp, err := srv.GetProviderCredential(settingsWriteCtx(org), &authv1.GetProviderCredentialRequest{
		OrgId: org, ProviderName: "anthropic",
	})
	if err != nil {
		t.Fatal(err)
	}
	assertGetCredResponse(t, resp)

	fake.getFn = func(context.Context, service.OrgProviderRef) (service.GetProviderCredentialResult, error) {
		return service.GetProviderCredentialResult{}, service.ErrProviderCredentialNotFound
	}
	_, err = srv.GetProviderCredential(settingsWriteCtx(org), &authv1.GetProviderCredentialRequest{
		OrgId: org, ProviderName: "openai",
	})
	assertGRPCCode(t, err, codes.NotFound)
}

func assertGetCredResponse(t *testing.T, resp *authv1.GetProviderCredentialResponse) {
	t.Helper()
	if resp.GetApiKey() != "sk-ant" {
		t.Fatalf("api_key=%q", resp.GetApiKey())
	}
	if resp.GetBaseUrl() != "https://byo.example" {
		t.Fatalf("base=%q", resp.GetBaseUrl())
	}
	if resp.GetIsPlatformDefault() {
		t.Fatal("expected BYO")
	}
}

func TestUnit_ListProviderCredentials_OK(t *testing.T) {
	t.Parallel()
	org := uuid.NewString()
	validated := time.Unix(1_700_000_000, 0).UTC()
	fake := &fakeCredAPI{
		listFn: func(_ context.Context, gotOrg string) ([]service.ProviderCredentialMetadata, error) {
			if gotOrg != org {
				t.Fatalf("org=%s", gotOrg)
			}
			return []service.ProviderCredentialMetadata{{
				ProviderName: "openai", Status: "active", KeyHint: "cdef",
				EncryptionKeyID: "v1", LastValidatedAt: &validated,
			}}, nil
		},
	}
	listed, err := newCredServer(t, fake).ListProviderCredentials(
		settingsWriteCtx(org), &authv1.ListProviderCredentialsRequest{OrgId: org},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(listed.GetCredentials()) != 1 {
		t.Fatalf("len=%d", len(listed.GetCredentials()))
	}
	if listed.GetCredentials()[0].GetKeyHint() != "cdef" {
		t.Fatalf("hint=%q", listed.GetCredentials()[0].GetKeyHint())
	}
	if listed.GetCredentials()[0].GetLastValidatedAt() == nil {
		t.Fatal("expected last_validated_at")
	}
}

func TestUnit_DeleteProviderCredentials_Paths(t *testing.T) {
	t.Parallel()
	org := uuid.NewString()
	fake := &fakeCredAPI{
		deleteFn: func(_ context.Context, ref service.OrgProviderRef) error {
			if ref.OrgID != org || ref.ProviderName != "openai" {
				t.Fatalf("ref=%+v", ref)
			}
			return nil
		},
	}
	srv := newCredServer(t, fake)
	_, err := srv.DeleteProviderCredential(settingsWriteCtx(org), &authv1.DeleteProviderCredentialRequest{
		OrgId: org, ProviderName: "openai",
	})
	if err != nil {
		t.Fatal(err)
	}
	fake.deleteFn = func(context.Context, service.OrgProviderRef) error {
		return service.ErrProviderCredentialNotFound
	}
	_, err = srv.DeleteProviderCredential(settingsWriteCtx(org), &authv1.DeleteProviderCredentialRequest{
		OrgId: org, ProviderName: "openai",
	})
	assertGRPCCode(t, err, codes.NotFound)
}

func TestUnit_ListProviderCredentials_Internal(t *testing.T) {
	t.Parallel()
	org := uuid.NewString()
	fake := &fakeCredAPI{
		listFn: func(context.Context, string) ([]service.ProviderCredentialMetadata, error) {
			return nil, errors.New("boom")
		},
	}
	_, err := newCredServer(t, fake).ListProviderCredentials(
		settingsWriteCtx(org), &authv1.ListProviderCredentialsRequest{OrgId: org},
	)
	assertGRPCCode(t, err, codes.Internal)
}

func TestUnit_DeleteAndListProviderCredentials_Authz(t *testing.T) {
	t.Parallel()
	org := uuid.NewString()
	srv := newCredServer(t, &fakeCredAPI{})

	_, err := srv.DeleteProviderCredential(context.Background(), &authv1.DeleteProviderCredentialRequest{
		OrgId: org, ProviderName: "openai",
	})
	assertGRPCCode(t, err, codes.Unauthenticated)

	_, err = srv.ListProviderCredentials(context.Background(), &authv1.ListProviderCredentialsRequest{OrgId: org})
	assertGRPCCode(t, err, codes.Unauthenticated)

	_, err = srv.DeleteProviderCredential(
		ContextWithCaller(context.Background(), CallerContext{OrgID: org, Permissions: permissions.ReadOnly}),
		&authv1.DeleteProviderCredentialRequest{OrgId: org, ProviderName: "openai"},
	)
	assertGRPCCode(t, err, codes.PermissionDenied)
}
