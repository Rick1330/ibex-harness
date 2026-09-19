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

type validateFieldSpec struct {
	num      protoreflect.FieldNumber
	name     string
	kind     protoreflect.Kind
	optional bool
	message  string
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
	specs := []validateFieldSpec{
		{1, "org_id", protoreflect.StringKind, false, ""},
		{2, "permissions", protoreflect.Int64Kind, false, ""},
		{3, "agent_id", protoreflect.StringKind, true, ""},
		{4, "user_id", protoreflect.StringKind, true, ""},
		{5, "token_id", protoreflect.StringKind, true, ""},
		{6, "expires_at", protoreflect.MessageKind, true, "google.protobuf.Timestamp"},
	}
	for _, spec := range specs {
		assertOneValidateField(t, resp, spec)
	}
}

func assertOneValidateField(t *testing.T, resp protoreflect.MessageDescriptor, spec validateFieldSpec) {
	t.Helper()
	f := fieldByNumber(resp, spec.num)
	if f == nil {
		t.Fatalf("response field %d (%s) missing", spec.num, spec.name)
	}
	if string(f.Name()) != spec.name {
		t.Errorf("field %d name: got %q want %q", spec.num, f.Name(), spec.name)
	}
	if f.Kind() != spec.kind {
		t.Errorf("field %s kind: got %v want %v", spec.name, f.Kind(), spec.kind)
	}
	if spec.optional && !f.HasOptionalKeyword() {
		t.Errorf("field %s should be optional", spec.name)
	}
	if spec.message != "" && string(f.Message().FullName()) != spec.message {
		t.Errorf("field %s message type: got %q want %q", spec.name, f.Message().FullName(), spec.message)
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
