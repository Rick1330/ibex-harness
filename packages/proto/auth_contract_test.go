package proto_test

import (
	"context"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/bufbuild/protocompile"
	"google.golang.org/protobuf/reflect/protoreflect"
	"google.golang.org/protobuf/types/descriptorpb"
)

func protoRoot(t *testing.T) string {
	t.Helper()
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Join(filepath.Dir(filename), "proto")
}

func compileProto(t *testing.T, relPath string) protoreflect.FileDescriptor {
	t.Helper()
	root := protoRoot(t)
	compiler := protocompile.Compiler{
		Resolver: protocompile.WithStandardImports(&protocompile.SourceResolver{
			ImportPaths: []string{root},
		}),
	}
	fds, err := compiler.Compile(context.Background(), relPath)
	if err != nil {
		t.Fatalf("compile %s: %v", relPath, err)
	}
	if len(fds) == 0 {
		t.Fatalf("no files compiled for %s", relPath)
	}
	return fds[0]
}

func findMessage(fd protoreflect.FileDescriptor, name string) protoreflect.MessageDescriptor {
	for i := 0; i < fd.Messages().Len(); i++ {
		md := fd.Messages().Get(i)
		if string(md.Name()) == name {
			return md
		}
	}
	return nil
}

func findService(fd protoreflect.FileDescriptor, name string) protoreflect.ServiceDescriptor {
	for i := 0; i < fd.Services().Len(); i++ {
		sd := fd.Services().Get(i)
		if string(sd.Name()) == name {
			return sd
		}
	}
	return nil
}

func fieldByNumber(md protoreflect.MessageDescriptor, num protoreflect.FieldNumber) protoreflect.FieldDescriptor {
	for i := 0; i < md.Fields().Len(); i++ {
		f := md.Fields().Get(i)
		if f.Number() == num {
			return f
		}
	}
	return nil
}

func TestAuthProtoContractADR0006(t *testing.T) {
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

	svc := findService(fd, "AuthService")
	if svc == nil {
		t.Fatal("AuthService not found")
	}
	wantMethods := []string{"ValidateToken", "CreateToken", "RevokeToken", "ListTokens"}
	if svc.Methods().Len() != len(wantMethods) {
		t.Fatalf("AuthService methods: got %d want %d", svc.Methods().Len(), len(wantMethods))
	}
	for i, name := range wantMethods {
		method := svc.Methods().Get(i)
		if string(method.Name()) != name {
			t.Errorf("RPC %d: got %q want %q", i, method.Name(), name)
		}
		if method.IsStreamingClient() || method.IsStreamingServer() {
			t.Errorf("%s must be unary", name)
		}
	}

	createResp := findMessage(fd, "CreateTokenResponse")
	if createResp == nil {
		t.Fatal("CreateTokenResponse not found")
	}
	plaintext := fieldByNumber(createResp, 2)
	if plaintext == nil || string(plaintext.Name()) != "plaintext" {
		t.Fatal("CreateTokenResponse.plaintext field missing")
	}

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

	resp := findMessage(fd, "ValidateTokenResponse")
	if resp == nil {
		t.Fatal("ValidateTokenResponse not found")
	}

	type fieldSpec struct {
		num      protoreflect.FieldNumber
		name     string
		kind     protoreflect.Kind
		optional bool
		message  string // for message kind
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

	if resp.Fields().Len() != 6 {
		t.Errorf("ValidateTokenResponse field count: got %d want 6", resp.Fields().Len())
	}

	// ADR-0006: no parallel REST error envelope messages in v1 auth proto
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

func TestContextProtoHasExpectedRPCCount(t *testing.T) {
	fd := compileProto(t, "ibex/context/v1/context.proto")

	svc := findService(fd, "ContextAssemblyService")
	if svc == nil {
		t.Fatal("ContextAssemblyService not found")
	}
	if svc.Methods().Len() != 3 {
		t.Fatalf("ContextAssemblyService RPC count: got %d want 3", svc.Methods().Len())
	}
}
