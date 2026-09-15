package proto_test

import (
	"strings"
	"testing"

	"google.golang.org/protobuf/reflect/protoreflect"
	"google.golang.org/protobuf/types/descriptorpb"
)

func TestAuthProtoPackageAndGoPackage(t *testing.T) {
	fd := compileProto(t, "ibex/auth/v1/auth.proto")
	if got := string(fd.Package()); got != "ibex.auth.v1" {
		t.Errorf("package: got %q want ibex.auth.v1", got)
	}
	if !strings.Contains(fd.Path(), "ibex/auth/v1/auth.proto") {
		t.Errorf("path: got %q", fd.Path())
	}
	opts, ok := fd.Options().(*descriptorpb.FileOptions)
	if !ok {
		t.Fatal("file options not *descriptorpb.FileOptions")
	}
	if !strings.HasSuffix(opts.GetGoPackage(), "/ibex/auth/v1;authv1") {
		t.Errorf("go_package: got %q", opts.GetGoPackage())
	}
}

func TestAuthProtoAuthServiceMethods(t *testing.T) {
	fd := compileProto(t, "ibex/auth/v1/auth.proto")
	svc := findService(fd, "AuthService")
	if svc == nil {
		t.Fatal("AuthService not found")
	}
	assertUnaryAuthMethods(t, svc, []string{
		"ValidateToken",
		"ValidateAgent",
		"CreateToken",
		"RevokeToken",
		"ListTokens",
		"CreateProviderCredential",
		"GetProviderCredential",
		"DeleteProviderCredential",
		"ListProviderCredentials",
		"BeginTotpEnrollment",
		"ConfirmTotpEnrollment",
		"CreateStepUpToken",
		"IssueOperatorSession",
	})
}

func TestAuthProtoCreateTokenPlaintext(t *testing.T) {
	fd := compileProto(t, "ibex/auth/v1/auth.proto")
	createResp := findMessage(fd, "CreateTokenResponse")
	if createResp == nil {
		t.Fatal("CreateTokenResponse not found")
	}
	plaintext := fieldByNumber(createResp, 2)
	if plaintext == nil || string(plaintext.Name()) != "plaintext" {
		t.Fatal("CreateTokenResponse.plaintext field missing")
	}
}

func TestAuthProtoValidateTokenRequest(t *testing.T) {
	fd := compileProto(t, "ibex/auth/v1/auth.proto")
	req := findMessage(fd, "ValidateTokenRequest")
	if req == nil {
		t.Fatal("ValidateTokenRequest not found")
	}
	accessToken := fieldByNumber(req, 1)
	if accessToken == nil || accessToken.Kind() != protoreflect.StringKind {
		t.Fatalf("access_token field 1: %+v", accessToken)
	}
	if string(accessToken.Name()) != "access_token" {
		t.Errorf("field 1 name: got %q", accessToken.Name())
	}
}

func TestAuthProtoValidateTokenResponseFields(t *testing.T) {
	fd := compileProto(t, "ibex/auth/v1/auth.proto")
	resp := findMessage(fd, "ValidateTokenResponse")
	if resp == nil {
		t.Fatal("ValidateTokenResponse not found")
	}
	assertValidateTokenResponseFields(t, resp)
	if resp.Fields().Len() != 6 {
		t.Errorf("ValidateTokenResponse field count: got %d want 6", resp.Fields().Len())
	}
}

func assertValidateTokenResponseFields(t *testing.T, resp protoreflect.MessageDescriptor) {
	t.Helper()
	type fieldSpec struct {
		num      protoreflect.FieldNumber
		name     string
		kind     protoreflect.Kind
		optional bool
		message  string
	}
	specs := []fieldSpec{
		{1, "org_id", protoreflect.StringKind, false, ""},
		{2, "permissions", protoreflect.Int64Kind, false, ""},
		{3, "agent_id", protoreflect.StringKind, true, ""},
		{4, "user_id", protoreflect.StringKind, true, ""},
		{5, "token_id", protoreflect.StringKind, true, ""},
		{6, "expires_at", protoreflect.MessageKind, true, "google.protobuf.Timestamp"},
	}
	for _, spec := range specs {
		assertOneValidateField(t, resp, spec.num, spec.name, spec.kind, spec.optional, spec.message)
	}
}

func assertOneValidateField(
	t *testing.T,
	resp protoreflect.MessageDescriptor,
	num protoreflect.FieldNumber,
	name string,
	kind protoreflect.Kind,
	optional bool,
	message string,
) {
	t.Helper()
	f := fieldByNumber(resp, num)
	if f == nil {
		t.Fatalf("response field %d (%s) missing", num, name)
	}
	if string(f.Name()) != name {
		t.Errorf("field %d name: got %q want %q", num, f.Name(), name)
	}
	if f.Kind() != kind {
		t.Errorf("field %s kind: got %v want %v", name, f.Kind(), kind)
	}
	if optional && !f.HasOptionalKeyword() {
		t.Errorf("field %s should be optional", name)
	}
	if message != "" && string(f.Message().FullName()) != message {
		t.Errorf("field %s message type: got %q want %q", name, f.Message().FullName(), message)
	}
}

func TestAuthProtoForbidsRESTErrorEnvelope(t *testing.T) {
	fd := compileProto(t, "ibex/auth/v1/auth.proto")
	forbidden := []string{"ErrorResponse", "ErrorDetail", "ApiError", "RestError"}
	for i := 0; i < fd.Messages().Len(); i++ {
		name := string(fd.Messages().Get(i).Name())
		for _, f := range forbidden {
			if name == f {
				t.Errorf("forbidden envelope message %q present", name)
			}
		}
	}
}
