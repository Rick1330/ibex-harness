package grpcserver

import (
	"context"
	"errors"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// providerCredentialAPI is the service port for provider credential RPCs.
type providerCredentialAPI interface {
	Create(ctx context.Context, in service.CreateInput) (service.ProviderCredentialMetadata, error)
	Get(ctx context.Context, orgID, providerName string) (service.GetProviderCredentialResult, error)
	List(ctx context.Context, orgID string) ([]service.ProviderCredentialMetadata, error)
	Delete(ctx context.Context, orgID, providerName string) error
}

func (s *Server) CreateProviderCredential(
	ctx context.Context,
	req *authv1.CreateProviderCredentialRequest,
) (*authv1.CreateProviderCredentialResponse, error) {
	if s.credService == nil {
		return nil, status.Error(codes.FailedPrecondition, "provider credentials not configured")
	}
	orgID := req.GetOrgId()
	if err := RequireOrgAndPermission(ctx, orgID, permissions.OrgSettingsWrite); err != nil {
		return nil, err
	}
	meta, err := s.credService.Create(ctx, service.CreateInput{
		OrgID:        orgID,
		ProviderName: req.GetProviderName(),
		APIKey:       req.GetApiKey(),
		BaseURL:      req.GetBaseUrl(),
	})
	if err != nil {
		return nil, mapProviderCredentialErr(err)
	}
	resp := &authv1.CreateProviderCredentialResponse{
		ProviderName:    meta.ProviderName,
		Status:          meta.Status,
		KeyHint:         meta.KeyHint,
		BaseUrl:         meta.BaseURL,
		EncryptionKeyId: meta.EncryptionKeyID,
	}
	if meta.LastValidatedAt != nil {
		resp.LastValidatedAt = timestamppb.New(*meta.LastValidatedAt)
	}
	return resp, nil
}

func (s *Server) GetProviderCredential(
	ctx context.Context,
	req *authv1.GetProviderCredentialRequest,
) (*authv1.GetProviderCredentialResponse, error) {
	if s.credService == nil {
		return nil, status.Error(codes.FailedPrecondition, "provider credentials not configured")
	}
	orgID := req.GetOrgId()
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return nil, status.Error(codes.Unauthenticated, errMsgMissingCallerContext)
	}
	if caller.OrgID != orgID {
		return nil, status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	result, err := s.credService.Get(ctx, orgID, req.GetProviderName())
	if err != nil {
		return nil, mapProviderCredentialErr(err)
	}
	return &authv1.GetProviderCredentialResponse{
		ApiKey:            result.APIKey,
		BaseUrl:           result.BaseURL,
		IsPlatformDefault: result.IsPlatformDefault,
	}, nil
}

func (s *Server) DeleteProviderCredential(
	ctx context.Context,
	req *authv1.DeleteProviderCredentialRequest,
) (*authv1.DeleteProviderCredentialResponse, error) {
	if s.credService == nil {
		return nil, status.Error(codes.FailedPrecondition, "provider credentials not configured")
	}
	orgID := req.GetOrgId()
	if err := RequireOrgAndPermission(ctx, orgID, permissions.OrgSettingsWrite); err != nil {
		return nil, err
	}
	if err := s.credService.Delete(ctx, orgID, req.GetProviderName()); err != nil {
		return nil, mapProviderCredentialErr(err)
	}
	return &authv1.DeleteProviderCredentialResponse{}, nil
}

func (s *Server) ListProviderCredentials(
	ctx context.Context,
	req *authv1.ListProviderCredentialsRequest,
) (*authv1.ListProviderCredentialsResponse, error) {
	if s.credService == nil {
		return nil, status.Error(codes.FailedPrecondition, "provider credentials not configured")
	}
	orgID := req.GetOrgId()
	if err := RequireOrgAndPermission(ctx, orgID, permissions.OrgSettingsWrite); err != nil {
		return nil, err
	}
	rows, err := s.credService.List(ctx, orgID)
	if err != nil {
		return nil, mapProviderCredentialErr(err)
	}
	out := make([]*authv1.ProviderCredentialMetadata, 0, len(rows))
	for _, row := range rows {
		item := &authv1.ProviderCredentialMetadata{
			ProviderName:    row.ProviderName,
			Status:          row.Status,
			KeyHint:         row.KeyHint,
			BaseUrl:         row.BaseURL,
			EncryptionKeyId: row.EncryptionKeyID,
		}
		if row.LastValidatedAt != nil {
			item.LastValidatedAt = timestamppb.New(*row.LastValidatedAt)
		}
		out = append(out, item)
	}
	return &authv1.ListProviderCredentialsResponse{Credentials: out}, nil
}

func mapProviderCredentialErr(err error) error {
	switch {
	case errors.Is(err, service.ErrProviderCredentialNotFound):
		return status.Error(codes.NotFound, "provider credential not found")
	case errors.Is(err, service.ErrCredentialsMasterKeyMissing):
		return status.Error(codes.FailedPrecondition, "provider credentials not configured")
	case errors.Is(err, service.ErrInvalidProviderName), errors.Is(err, service.ErrEmptyAPIKey):
		return status.Error(codes.InvalidArgument, errMsgInvalidRequest)
	default:
		return status.Error(codes.Internal, "provider credential operation failed")
	}
}
