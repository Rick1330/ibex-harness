//go:build integration

package proxy_test

import (
	"context"
	"io"
	"net/http"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

type mockForwardingProvider struct{}

func (mockForwardingProvider) Name() string { return "mock" }

func (mockForwardingProvider) SupportedModels() []string { return []string{"gpt-4o"} }

func (mockForwardingProvider) Complete(_ context.Context, _ provider.Request) (provider.Response, error) {
	return provider.Response{
		StatusCode: http.StatusOK,
		Body:       io.NopCloser(strings.NewReader(`{"id":"test","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"ok"},"finish_reason":"stop"}]}`)),
	}, nil
}
