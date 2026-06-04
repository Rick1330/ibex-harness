//go:build integration

package testutil

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc/metadata"
)

// SeedTokenViaCreateToken creates a PAT through the real CreateToken RPC (preferred over SQL SeedToken).
func SeedTokenViaCreateToken(
	t testing.TB,
	client authv1.AuthServiceClient,
	adminBearer, orgID string,
	perms int64,
) (plaintext, tokenID string) {
	t.Helper()
	ctx := metadata.NewOutgoingContext(context.Background(), metadata.Pairs(
		"authorization", "Bearer "+adminBearer,
	))
	resp, err := client.CreateToken(ctx, &authv1.CreateTokenRequest{
		OrgId:       orgID,
		Name:        "testutil-seed",
		Type:        authv1.TokenType_TOKEN_TYPE_PAT,
		Permissions: perms,
	})
	if err != nil {
		t.Fatalf("SeedTokenViaCreateToken: %v", err)
	}
	if resp.GetPlaintext() == "" || resp.GetTokenId() == "" {
		t.Fatal("SeedTokenViaCreateToken: empty response")
	}
	return resp.GetPlaintext(), resp.GetTokenId()
}

// SeedAgentTokenViaCreateToken seeds a token with AgentDefault permissions.
func SeedAgentTokenViaCreateToken(t testing.TB, client authv1.AuthServiceClient, adminBearer, orgID string) (plaintext, tokenID string) {
	t.Helper()
	return SeedTokenViaCreateToken(t, client, adminBearer, orgID, permissions.AgentDefault)
}
