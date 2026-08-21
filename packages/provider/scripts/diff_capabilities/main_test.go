package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRun_FileMissingLimitsIsMismatch(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	path := filepath.Join(dir, "snapshot.json")
	// gpt-4o present but no max_input_tokens / max_output_tokens.
	body := `{
		"gpt-4o": {"max_tokens": 16384},
		"gpt-4o-mini": {"max_input_tokens": 128000, "max_output_tokens": 16384},
		"gpt-4-turbo": {"max_input_tokens": 128000, "max_output_tokens": 4096},
		"gpt-3.5-turbo": {"max_input_tokens": 16385, "max_output_tokens": 4096},
		"claude-sonnet-4-5": {"max_input_tokens": 200000, "max_output_tokens": 64000},
		"claude-haiku-4-5": {"max_input_tokens": 200000, "max_output_tokens": 64000},
		"claude-opus-4-5": {"max_input_tokens": 200000, "max_output_tokens": 64000}
	}`
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	var stdout, stderr bytes.Buffer
	code := run([]string{"-file", path}, &stdout, &stderr)
	if code != 1 {
		t.Fatalf("exit=%d stdout=%s stderr=%s", code, stdout.String(), stderr.String())
	}
	if !strings.Contains(stdout.String(), "NO_LIMITS_UPSTREAM\tgpt-4o") {
		t.Fatalf("stdout=%s", stdout.String())
	}
}

func TestRun_MatchingSnapshotOK(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	path := filepath.Join(dir, "snapshot.json")
	body := `{
		"gpt-4o": {"max_input_tokens": 128000, "max_output_tokens": 16384},
		"gpt-4o-mini": {"max_input_tokens": 128000, "max_output_tokens": 16384},
		"gpt-4-turbo": {"max_input_tokens": 128000, "max_output_tokens": 4096},
		"gpt-3.5-turbo": {"max_input_tokens": 16385, "max_output_tokens": 4096},
		"claude-sonnet-4-5": {"max_input_tokens": 200000, "max_output_tokens": 64000},
		"claude-haiku-4-5": {"max_input_tokens": 200000, "max_output_tokens": 64000},
		"claude-opus-4-5": {"max_input_tokens": 200000, "max_output_tokens": 64000}
	}`
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	var stdout, stderr bytes.Buffer
	code := run([]string{"-file", path}, &stdout, &stderr)
	if code != 0 {
		t.Fatalf("exit=%d stdout=%s stderr=%s", code, stdout.String(), stderr.String())
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
