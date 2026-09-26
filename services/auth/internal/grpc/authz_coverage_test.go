package grpcserver

import (
	"context"
	"testing"

	"google.golang.org/grpc/metadata"
)

func TestValidServiceToken(t *testing.T) {
	t.Parallel()
	if validServiceToken(context.Background(), "") {
		t.Fatal("empty expected")
	}
	if validServiceToken(context.Background(), "secret") {
		t.Fatal("no metadata")
	}
	md := metadata.Pairs(serviceTokenMetadataKey, "a", serviceTokenMetadataKey, "b")
	ctx := metadata.NewIncomingContext(context.Background(), md)
	if validServiceToken(ctx, "secret") {
		t.Fatal("multiple values")
	}
	md = metadata.Pairs(serviceTokenMetadataKey, "")
	ctx = metadata.NewIncomingContext(context.Background(), md)
	if validServiceToken(ctx, "secret") {
		t.Fatal("empty value")
	}
	md = metadata.Pairs(serviceTokenMetadataKey, "wrong")
	ctx = metadata.NewIncomingContext(context.Background(), md)
	if validServiceToken(ctx, "secret") {
		t.Fatal("wrong secret")
	}
	md = metadata.Pairs(serviceTokenMetadataKey, "secret")
	ctx = metadata.NewIncomingContext(context.Background(), md)
	if !validServiceToken(ctx, "secret") {
		t.Fatal("expected match")
	}
}

func TestIsServiceLifecycleMethod(t *testing.T) {
	t.Parallel()
	if !isServiceLifecycleMethod("/ibex.auth.v1.AuthService/IssueOperatorSession") {
		t.Fatal("IssueOperatorSession should be lifecycle")
	}
	if !isServiceLifecycleMethod("/ibex.auth.v1.AuthService/ValidateOperatorSession") {
		t.Fatal("ValidateOperatorSession should be lifecycle")
	}
	if isServiceLifecycleMethod("/ibex.auth.v1.AuthService/ValidateToken") {
		t.Fatal("ValidateToken must not be lifecycle")
	}
}
