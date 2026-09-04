package main

import (
	"bytes"
	"errors"
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

func TestUnit_ParseExportArgs(t *testing.T) {
	t.Parallel()
	var stderr bytes.Buffer
	out, check, code := parseExportArgs([]string{"-o", "a.json", "-check", "b.json"}, &stderr)
	if code != 2 || out != "" || check != "" {
		t.Fatalf("both flags: code=%d out=%q check=%q", code, out, check)
	}
	stderr.Reset()
	out, check, code = parseExportArgs([]string{"-bogus"}, &stderr)
	if code != 2 {
		t.Fatalf("bad flag exit=%d", code)
	}
	out, check, code = parseExportArgs([]string{"-o", filepath.Join("x", catalogFileName)}, &stderr)
	if code != 0 || out == "" || check != "" {
		t.Fatalf("out only: code=%d out=%q check=%q", code, out, check)
	}
}

func TestUnit_ResolveCatalogPath(t *testing.T) {
	t.Parallel()
	if _, err := resolveCatalogPath(""); err == nil {
		t.Fatal("empty path should fail")
	}
	if _, err := resolveCatalogPath("."); err == nil {
		t.Fatal("dot path should fail")
	}
	if _, err := resolveCatalogPath("evil.txt"); err == nil {
		t.Fatal("wrong leaf should fail")
	}
	path := filepath.Join(t.TempDir(), catalogFileName)
	got, err := resolveCatalogPath(path)
	if err != nil {
		t.Fatal(err)
	}
	if filepath.Base(got) != catalogFileName {
		t.Fatalf("base=%q", filepath.Base(got))
	}
}

func TestUnit_ResolveCatalogPath_AbsFailure(t *testing.T) {
	prev := filepathAbs
	t.Cleanup(func() { filepathAbs = prev })
	filepathAbs = func(string) (string, error) { return "", errors.New("abs boom") }
	if _, err := resolveCatalogPath(catalogFileName); err == nil {
		t.Fatal("expected abs failure")
	}
}

func TestUnit_ResolveCatalogPath_AbsWrongLeaf(t *testing.T) {
	prev := filepathAbs
	t.Cleanup(func() { filepathAbs = prev })
	filepathAbs = func(string) (string, error) { return "/tmp/not-the-catalog.json", nil }
	if _, err := resolveCatalogPath(catalogFileName); err == nil {
		t.Fatal("expected leaf rejection after abs")
	}
}
