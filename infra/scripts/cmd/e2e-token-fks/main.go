// Command e2e-token-fks exercises CreateToken subject-org binds against a live
// auth gRPC server (compose-dev). Not a unit test — run via the wave2b E2E script.
package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "FAIL: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("PASS: CreateToken subject-org E2E matrix")
}

func run() error {
	cfg, err := loadCfg()
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	conn, err := grpc.NewClient(cfg.addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return fmt.Errorf("dial auth: %w", err)
	}
	defer func() { _ = conn.Close() }()
	client := authv1.NewAuthServiceClient(conn)

	cases := []createCase{
		{label: "cross-org agent_id", agentID: &cfg.agentB},
		{label: "cross-org user_id", userID: &cfg.userB},
		{label: "missing agent_id", agentID: &cfg.missingID},
	}
	for _, c := range cases {
		if err := assertDenied(ctx, client, cfg, c); err != nil {
			return err
		}
	}
	plain, err := assertSameOrgOK(ctx, client, cfg)
	if err != nil {
		return err
	}
	return assertValidateBound(ctx, client, plain, cfg)
}

type e2eCfg struct {
	addr, bearer, orgA           string
	userA, userB, agentA, agentB string
	missingID                    string
}

type createCase struct {
	label           string
	agentID, userID *string
}

func loadCfg() (e2eCfg, error) {
	cfg := e2eCfg{
		addr:      envOr("IBEX_AUTH_GRPC_ADDR", "127.0.0.1:9091"),
		bearer:    envOr("IBEX_DEV_TOKEN", "ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY"),
		orgA:      envOr("IBEX_DEV_ORG_ID", "00000000-0000-0000-0000-000000000001"),
		userA:     envOr("IBEX_DEV_USER_ID", "00000000-0000-0000-0000-000000000002"),
		agentA:    envOr("IBEX_DEV_AGENT_ID", "00000000-0000-0000-0000-000000000003"),
		userB:     os.Getenv("IBEX_E2E_USER_B"),
		agentB:    os.Getenv("IBEX_E2E_AGENT_B"),
		missingID: "00000000-0000-0000-0000-00000000dead",
	}
	if cfg.userB == "" || cfg.agentB == "" {
		return cfg, fmt.Errorf("IBEX_E2E_USER_B and IBEX_E2E_AGENT_B required (seeded by E2E script)")
	}
	return cfg, nil
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func authCtx(ctx context.Context, bearer string) context.Context {
	return metadata.NewOutgoingContext(ctx, metadata.Pairs("authorization", "Bearer "+bearer))
}

func assertDenied(ctx context.Context, client authv1.AuthServiceClient, cfg e2eCfg, c createCase) error {
	_, err := client.CreateToken(authCtx(ctx, cfg.bearer), &authv1.CreateTokenRequest{
		OrgId: cfg.orgA, Name: "e2e-" + c.label, Type: authv1.TokenType_TOKEN_TYPE_PAT,
		Permissions: permissions.AgentDefault, AgentId: c.agentID, UserId: c.userID,
	})
	if status.Code(err) != codes.PermissionDenied {
		return fmt.Errorf("%s: want PERMISSION_DENIED, got code=%v err=%v", c.label, status.Code(err), err)
	}
	fmt.Printf("PASS: CreateToken %s → PERMISSION_DENIED\n", c.label)
	return nil
}

func assertSameOrgOK(ctx context.Context, client authv1.AuthServiceClient, cfg e2eCfg) (string, error) {
	resp, err := client.CreateToken(authCtx(ctx, cfg.bearer), &authv1.CreateTokenRequest{
		OrgId: cfg.orgA, Name: "e2e-same-org-bind", Type: authv1.TokenType_TOKEN_TYPE_PAT,
		Permissions: permissions.AgentDefault, AgentId: &cfg.agentA, UserId: &cfg.userA,
	})
	if err != nil {
		return "", fmt.Errorf("same-org bind: %w", err)
	}
	plain := resp.GetPlaintext()
	if plain == "" {
		return "", fmt.Errorf("same-org bind: empty plaintext")
	}
	fmt.Println("PASS: CreateToken same-org agent+user bind → OK")
	return plain, nil
}

func assertValidateBound(ctx context.Context, client authv1.AuthServiceClient, plain string, cfg e2eCfg) error {
	val, err := client.ValidateToken(ctx, &authv1.ValidateTokenRequest{AccessToken: plain})
	if err != nil {
		return fmt.Errorf("ValidateToken minted PAT: %w", err)
	}
	if val.GetAgentId() != cfg.agentA {
		return fmt.Errorf("ValidateToken agent=%q want %q", val.GetAgentId(), cfg.agentA)
	}
	if val.GetUserId() != cfg.userA {
		return fmt.Errorf("ValidateToken user=%q want %q", val.GetUserId(), cfg.userA)
	}
	fmt.Println("PASS: ValidateToken returns bound agent_id and user_id")
	return nil
}
