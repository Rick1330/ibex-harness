package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestUnit_CheckFresh_DetectsDrift(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	path := filepath.Join(dir, catalogFileName)
	doc := buildExport(provider.BuiltInCapabilityCatalog())
	raw, err := marshalCanonical(doc)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		t.Fatal(err)
	}
	if code := checkFresh(path, raw, ioDiscard{}); code != 0 {
		t.Fatalf("fresh check exit=%d want 0", code)
	}
	mutated := bytes.Replace(raw, []byte(`"context_window": 128000`), []byte(`"context_window": 1`), 1)
	if bytes.Equal(mutated, raw) {
		t.Fatal("mutation did not change bytes — fixture assumption broken")
	}
	if err := os.WriteFile(path, mutated, 0o644); err != nil {
		t.Fatal(err)
	}
	if code := checkFresh(path, raw, ioDiscard{}); code != 1 {
		t.Fatalf("drift check exit=%d want 1", code)
	}
}

func TestUnit_CheckFresh_PathAndReadErrors(t *testing.T) {
	t.Parallel()
	raw := []byte(`{}`)
	if code := checkFresh("bad-name.json", raw, ioDiscard{}); code != 2 {
		t.Fatalf("bad path exit=%d", code)
	}
	missing := filepath.Join(t.TempDir(), catalogFileName)
	if code := checkFresh(missing, raw, ioDiscard{}); code != 2 {
		t.Fatalf("missing file exit=%d", code)
	}
}

func TestUnit_Run_CheckMode(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	path := filepath.Join(dir, catalogFileName)
	doc := buildExport(provider.BuiltInCapabilityCatalog())
	raw, err := marshalCanonical(doc)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		t.Fatal(err)
	}
	var stdout, stderr bytes.Buffer
	if code := run([]string{"-check", path}, &stdout, &stderr); code != 0 {
		t.Fatalf("run -check exit=%d stderr=%s", code, stderr.String())
	}
	mutated := append([]byte{}, raw...)
	mutated = bytes.Replace(mutated, []byte(`"gpt-4o"`), []byte(`"gpt-4o-mutated"`), 1)
	if err := os.WriteFile(path, mutated, 0o644); err != nil {
		t.Fatal(err)
	}
	if code := run([]string{"-check", path}, &stdout, &stderr); code != 1 {
		t.Fatalf("run -check drift exit=%d want 1", code)
	}
}

func TestUnit_Run_MarshalFailure(t *testing.T) {
	prev := jsonEncode
	t.Cleanup(func() { jsonEncode = prev })
	jsonEncode = func(_ *json.Encoder, _ any) error {
		return errors.New("encode boom")
	}
	var stdout, stderr bytes.Buffer
	if code := run(nil, &stdout, &stderr); code != 2 {
		t.Fatalf("marshal failure exit=%d want 2 stderr=%s", code, stderr.String())
	}
}
