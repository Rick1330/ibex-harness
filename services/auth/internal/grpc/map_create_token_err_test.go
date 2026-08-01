package grpcserver

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestUnit_MapCreateTokenServiceErr(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name     string
		err      error
		wantCode codes.Code
		wantMsg  string
	}{
		{
			name:     "invalid_argument",
			err:      service.ErrInvalidArgument,
			wantCode: codes.InvalidArgument,
			wantMsg:  errMsgInvalidRequest,
		},
		{
			name:     "subject_forbidden",
			err:      service.ErrTokenSubjectForbidden,
			wantCode: codes.PermissionDenied,
			wantMsg:  errMsgForbidden,
		},
		{
			name:     "deadline",
			err:      context.DeadlineExceeded,
			wantCode: codes.DeadlineExceeded,
			wantMsg:  "create token timed out",
		},
		{
			name:     "canceled",
			err:      context.Canceled,
			wantCode: codes.Canceled,
			wantMsg:  "create token canceled",
		},
		{
			name:     "internal_opaque",
			err:      errors.New("db connection refused"),
			wantCode: codes.Internal,
			wantMsg:  "create token failed",
		},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			s := &Server{log: logger.Discard("auth")}
			err := s.mapCreateTokenServiceErr(context.Background(), tc.err)
			st, ok := status.FromError(err)
			if !ok {
				t.Fatalf("not status: %v", err)
			}
			assertStatusCodeMsg(t, st, tc.wantCode, tc.wantMsg)
			if strings.Contains(st.Message(), "db connection") {
				t.Fatal("internal details leaked to caller")
			}
		})
	}
}

func TestUnit_CreateToken_UppercaseOrgIDNormalized(t *testing.T) {
	t.Parallel()
	orgID := "00000000-0000-4000-8000-0000000000aa"
	tc := createTokenCase{
		name: "ok uppercase org_id",
		ctx: ContextWithCaller(context.Background(), CallerContext{
			OrgID: orgID, Permissions: permissions.Admin,
		}),
		req: &authv1.CreateTokenRequest{
			OrgId: strings.ToUpper(orgID), Name: "cased",
			Permissions: permissions.AgentDefault,
		},
		wantCode: codes.OK,
	}
	runCreateTokenCase(t, tc)
}
