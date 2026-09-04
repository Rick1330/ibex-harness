package main

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestUnit_BuildExport_SortedAndComplete(t *testing.T) {
	t.Parallel()
	doc := buildExport(provider.BuiltInCapabilityCatalog())
	if doc.SchemaVersion != 1 {
		t.Fatalf("schema_version=%d", doc.SchemaVersion)
	}
	if doc.Source != sourceLabel {
		t.Fatalf("source=%q", doc.Source)
	}
	catalog := provider.BuiltInCapabilityCatalog()
	if len(doc.Models) != len(catalog) {
		t.Fatalf("models=%d catalog=%d", len(doc.Models), len(catalog))
	}
	for i := 1; i < len(doc.Models); i++ {
		if doc.Models[i-1].ModelID >= doc.Models[i].ModelID {
			t.Fatalf("models not sorted at %d: %q then %q", i, doc.Models[i-1].ModelID, doc.Models[i].ModelID)
		}
	}
	for _, fam := range []string{
		provider.TokenizerFamilyO200kBase,
		provider.TokenizerFamilyCL100kBase,
		provider.TokenizerFamilyClaude,
		provider.TokenizerFamilyUnknown,
	} {
		if _, ok := doc.TokenizerFamilies[fam]; !ok {
			t.Fatalf("missing tokenizer family policy %q", fam)
		}
	}
}

func TestUnit_CheckFresh_DetectsDrift(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	path := filepath.Join(dir, "model_capabilities.v1.json")
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

func TestUnit_Run_CheckMode(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	path := filepath.Join(dir, "model_capabilities.v1.json")
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

func TestUnit_WriteAtomic_AndStdoutChecks(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	path := filepath.Join(dir, "model_capabilities.v1.json")
	var stdout, stderr bytes.Buffer
	if code := run([]string{"-o", path}, &stdout, &stderr); code != 0 {
		t.Fatalf("run -o exit=%d stderr=%s", code, stderr.String())
	}
	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	want, err := marshalCanonical(buildExport(provider.BuiltInCapabilityCatalog()))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(normalizeNewline(got), normalizeNewline(want)) {
		t.Fatalf("atomic write mismatch")
	}

	stdout.Reset()
	stderr.Reset()
	if code := run(nil, &stdout, &stderr); code != 0 {
		t.Fatalf("stdout export exit=%d stderr=%s", code, stderr.String())
	}
	if !bytes.Equal(normalizeNewline(stdout.Bytes()), normalizeNewline(want)) {
		t.Fatalf("stdout export mismatch")
	}

	stderr.Reset()
	if code := run(nil, shortWriter{}, &stderr); code != 2 {
		t.Fatalf("short write exit=%d want 2 stderr=%s", code, stderr.String())
	}
	stderr.Reset()
	if code := run(nil, errWriter{}, &stderr); code != 2 {
		t.Fatalf("error write exit=%d want 2 stderr=%s", code, stderr.String())
	}
}

type ioDiscard struct{}

func (ioDiscard) Write(p []byte) (int, error) { return len(p), nil }

type shortWriter struct{}

func (shortWriter) Write(p []byte) (int, error) {
	if len(p) == 0 {
		return 0, nil
	}
	return len(p) - 1, nil
}

type errWriter struct{}

func (errWriter) Write([]byte) (int, error) { return 0, os.ErrClosed }
