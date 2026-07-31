package grpcserver

import (
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// tokenListToProto maps service metadata to proto messages.
func tokenListToProto(rows []service.TokenListItem) []*authv1.TokenMetadata {
	out := make([]*authv1.TokenMetadata, 0, len(rows))
	for _, row := range rows {
		m := &authv1.TokenMetadata{
			TokenId:     row.ID,
			Name:        row.Name,
			Prefix:      row.Prefix,
			Permissions: row.Permissions,
			CreatedAt:   timestamppb.New(row.CreatedAt.UTC()),
			IsRevoked:   row.IsRevoked,
		}
		if row.ExpiresAt != nil {
			m.ExpiresAt = timestamppb.New(row.ExpiresAt.UTC())
		}
		if row.RevokedAt != nil {
			m.RevokedAt = timestamppb.New(row.RevokedAt.UTC())
		}
		out = append(out, m)
	}
	return out
}
