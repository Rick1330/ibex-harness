package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// curatedLimits is the matching LiteLLM shape for BuiltInCapabilityCatalog.
var curatedLimits = map[string]map[string]any{
	"gpt-4o":            {"max_input_tokens": 128000, "max_output_tokens": 16384},
	"gpt-4o-mini":       {"max_input_tokens": 128000, "max_output_tokens": 16384},
	"gpt-4-turbo":       {"max_input_tokens": 128000, "max_output_tokens": 4096},
	"gpt-3.5-turbo":     {"max_input_tokens": 16385, "max_output_tokens": 4096},
	"claude-sonnet-4-5": {"max_input_tokens": 200000, "max_output_tokens": 64000},
	"claude-haiku-4-5":  {"max_input_tokens": 200000, "max_output_tokens": 64000},
	"claude-opus-4-5":   {"max_input_tokens": 200000, "max_output_tokens": 64000},
}

func cloneCuratedLimits() map[string]map[string]any {
	out := make(map[string]map[string]any, len(curatedLimits))
	for id, limits := range curatedLimits {
		out[id] = cloneLimitRow(limits)
	}
	return out
}

func cloneLimitRow(limits map[string]any) map[string]any {
	cp := make(map[string]any, len(limits))
	for k, v := range limits {
		cp[k] = v
	}
	return cp
}

func applySnapshotOverrides(out, overrides map[string]map[string]any) {
	for id, limits := range overrides {
		applyOneOverride(out, id, limits)
	}
}

func applyOneOverride(out map[string]map[string]any, id string, limits map[string]any) {
	if limits == nil {
		delete(out, id)
		return
	}
	out[id] = limits
}

func omitSnapshotModels(out map[string]map[string]any, omit []string) {
	for _, id := range omit {
		delete(out, id)
	}
}

// snapshotJSON builds a LiteLLM-style catalog JSON from curated defaults plus
// optional omissions and per-model overrides (nil override value deletes the model).
func snapshotJSON(omit []string, overrides map[string]map[string]any) string {
	out := cloneCuratedLimits()
	omitSnapshotModels(out, omit)
	applySnapshotOverrides(out, overrides)
	raw, err := json.Marshal(out)
	if err != nil {
		panic(err)
	}
	return string(raw)
}

func matchingSnapshot() string {
	return snapshotJSON(nil, nil)
}

func writeSnapshot(t *testing.T, body string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "snapshot.json")
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func runSnapshot(t *testing.T, body string) (code int, stdout string) {
	t.Helper()
	path := writeSnapshot(t, body)
	var out, errBuf bytes.Buffer
	code = run([]string{"-file", path}, &out, &errBuf)
	return code, out.String()
}

func TestRun_MismatchCases(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name    string
		body    string
		wantSub []string
	}{
		{
			name:    "no limits",
			body:    snapshotJSON(nil, map[string]map[string]any{"gpt-4o": {"max_tokens": 16384}}),
			wantSub: []string{"NO_LIMITS_UPSTREAM\tgpt-4o"},
		},
		{
			name: "context and max out",
			body: snapshotJSON(nil, map[string]map[string]any{
				"gpt-4o": {"max_input_tokens": 999, "max_output_tokens": 1},
			}),
			wantSub: []string{"CONTEXT_MISMATCH\tgpt-4o", "MAX_OUT_MISMATCH\tgpt-4o"},
		},
		{
			name:    "missing upstream",
			body:    snapshotJSON([]string{"gpt-4o"}, nil),
			wantSub: []string{"MISSING_UPSTREAM\tgpt-4o"},
		},
		{
			name: "invalid upstream limits",
			body: snapshotJSON(nil, map[string]map[string]any{
				"gpt-4o": {"max_input_tokens": 128000.5, "max_output_tokens": 1e20},
			}),
			wantSub: []string{"INVALID_UPSTREAM_CONTEXT\tgpt-4o", "INVALID_UPSTREAM_MAX_OUT\tgpt-4o"},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			assertMismatchRun(t, tc.body, tc.wantSub)
		})
	}
}

func assertMismatchRun(t *testing.T, body string, wantSub []string) {
	t.Helper()
	code, stdout := runSnapshot(t, body)
	requireExitCode(t, code, 1, stdout)
	requireStdoutContainsAll(t, stdout, wantSub)
}

func requireExitCode(t *testing.T, got, want int, stdout string) {
	t.Helper()
	if got != want {
		t.Fatalf("exit=%d want %d stdout=%s", got, want, stdout)
	}
}

func requireStdoutContainsAll(t *testing.T, stdout string, wantSub []string) {
	t.Helper()
	for _, sub := range wantSub {
		requireStdoutContains(t, stdout, sub)
	}
}

func requireStdoutContains(t *testing.T, stdout, sub string) {
	t.Helper()
	if !strings.Contains(stdout, sub) {
		t.Fatalf("stdout=%s want %q", stdout, sub)
	}
}

func TestRun_MatchingSnapshotOK(t *testing.T) {
	t.Parallel()
	code, stdout := runSnapshot(t, matchingSnapshot())
	if code != 0 {
		t.Fatalf("exit=%d stdout=%s", code, stdout)
	}
}

func TestRun_RequiresFileOrFetch(t *testing.T) {
	t.Parallel()
	var stdout, stderr bytes.Buffer
	code := run(nil, &stdout, &stderr)
	if code != 2 {
		t.Fatalf("exit=%d", code)
	}
}

func TestRun_InvalidJSON(t *testing.T) {
	t.Parallel()
	code, _ := runSnapshot(t, `{`)
	if code != 2 {
		t.Fatalf("exit=%d", code)
	}
}

func TestRun_MissingFile(t *testing.T) {
	t.Parallel()
	var stdout, stderr bytes.Buffer
	code := run([]string{"-file", filepath.Join(t.TempDir(), "missing.json")}, &stdout, &stderr)
	if code != 2 {
		t.Fatalf("exit=%d", code)
	}
}

func TestLoadLiteLLMFrom_FetchOKAndError(t *testing.T) {
	t.Parallel()
	okSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{}`))
	}))
	t.Cleanup(okSrv.Close)
	raw, err := loadLiteLLMFrom("", true, okSrv.URL)
	if err != nil || string(raw) != "{}" {
		t.Fatalf("ok: raw=%q err=%v", raw, err)
	}

	badSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
	}))
	t.Cleanup(badSrv.Close)
	if _, err := loadLiteLLMFrom("", true, badSrv.URL); err == nil || !strings.Contains(err.Error(), "status") {
		t.Fatalf("bad status err=%v", err)
	}

	if _, err := loadLiteLLMFrom("", true, "http://127.0.0.1:1"); err == nil {
		t.Fatal("expected dial error")
	}
}

func TestLoadLiteLLM_FilePath(t *testing.T) {
	t.Parallel()
	path := writeSnapshot(t, `{}`)
	raw, err := loadLiteLLM(path, false)
	if err != nil || string(raw) != "{}" {
		t.Fatalf("raw=%q err=%v", raw, err)
	}
}

func TestMain_ExitsWithRunCode(t *testing.T) {
	oldExit := exitFunc
	oldArgs := os.Args
	t.Cleanup(func() {
		exitFunc = oldExit
		os.Args = oldArgs
	})
	var code int
	exitFunc = func(c int) { code = c }
	os.Args = []string{"diff_capabilities"}
	main()
	if code != 2 {
		t.Fatalf("exit=%d want 2 (missing -file/-fetch)", code)
	}
}

func TestParseUpstreamLimit(t *testing.T) {
	t.Parallel()
	neg, huge, frac := -1.0, 1e20, 1.5
	zero, ok := 0.0, 128000.0
	cases := []struct {
		in      *float64
		want    int
		invalid bool
	}{
		{nil, 0, false},
		{&zero, 0, false},
		{&ok, 128000, false},
		{&neg, 0, true},
		{&frac, 0, true},
		{&huge, 0, true},
	}
	for _, tc := range cases {
		got, invalid := parseUpstreamLimit(tc.in)
		if got != tc.want || invalid != tc.invalid {
			t.Fatalf("in=%v got=(%d,%v) want=(%d,%v)", tc.in, got, invalid, tc.want, tc.invalid)
		}
	}
}
