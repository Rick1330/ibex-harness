package proto_test

import (
	"context"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/bufbuild/protocompile"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protoreflect"
	"google.golang.org/protobuf/types/known/timestamppb"
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

func assertUnaryAuthMethods(t *testing.T, svc protoreflect.ServiceDescriptor, want []string) {
	t.Helper()
	if svc.Methods().Len() != len(want) {
		t.Fatalf("AuthService methods: got %d want %d", svc.Methods().Len(), len(want))
	}
	for i, name := range want {
		method := svc.Methods().Get(i)
		if string(method.Name()) != name {
			t.Errorf("RPC %d: got %q want %q", i, method.Name(), name)
		}
		if method.IsStreamingClient() || method.IsStreamingServer() {
			t.Errorf("%s must be unary", name)
		}
	}
}

func protoRoundTrip(t *testing.T, msg proto.Message) {
	t.Helper()
	data, err := proto.Marshal(msg)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	out := proto.Clone(msg)
	proto.Reset(out)
	if err := proto.Unmarshal(data, out); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if !proto.Equal(msg, out) {
		t.Fatalf("round-trip mismatch:\n  got  %v\n  want %v", out, msg)
	}
}

func strPtr(s string) *string { return &s }

func sampleTimestamp() *timestamppb.Timestamp {
	return timestamppb.Now()
}

func runAuthMessageRoundTrips(t *testing.T, cases []authMessageCase) {
	t.Helper()
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			protoRoundTrip(t, tc.msg)
		})
	}
}

func TestAuthValidateMessagesProtoRoundTrip(t *testing.T) {
	t.Parallel()
	runAuthMessageRoundTrips(t, authValidateMessageCases(sampleTimestamp()))
}

func TestAuthTokenMessagesProtoRoundTrip(t *testing.T) {
	t.Parallel()
	runAuthMessageRoundTrips(t, authTokenMessageCases(sampleTimestamp()))
}

func TestAuthListMessagesProtoRoundTrip(t *testing.T) {
	t.Parallel()
	runAuthMessageRoundTrips(t, authListMessageCases(sampleTimestamp()))
}
