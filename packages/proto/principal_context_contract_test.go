package proto_test

import (
	"google.golang.org/protobuf/reflect/protoreflect"
	"testing"
)

func TestPrincipalContextContractIsAdditiveAndStable(t *testing.T) {
	t.Parallel()
	fd := compileProto(t, "ibex/auth/v1/principal_context.proto")
	if got, want := string(fd.Package()), "ibex.auth.v1"; got != want {
		t.Fatalf("package: got %q want %q", got, want)
	}
	principal := findMessage(fd, "PrincipalContext")
	if principal == nil {
		t.Fatal("PrincipalContext message missing")
	}
	want := map[protoreflect.FieldNumber]string{1: "org_id", 2: "principal_id", 3: "agent_id", 4: "principal_type", 5: "authz_snapshot_id", 6: "authz_snapshot_digest", 7: "authority", 8: "issued_at", 9: "expires_at", 10: "request_id", 11: "trace_id", 12: "source", 13: "permissions", 14: "token_id"}
	if got := principal.Fields().Len(); got != len(want) {
		t.Fatalf("field count: got %d want %d", got, len(want))
	}
	for number, name := range want {
		field := fieldByNumber(principal, number)
		if field == nil || string(field.Name()) != name {
			t.Errorf("field %d: got %v want %q", number, field, name)
		}
	}
}
