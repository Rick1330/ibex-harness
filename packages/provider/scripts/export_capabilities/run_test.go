package main

import (
	"bytes"
	"os"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

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

func TestUnit_Run_BothFlagsRejected(t *testing.T) {
	t.Parallel()
	var stdout, stderr bytes.Buffer
	if code := run([]string{"-o", catalogFileName, "-check", catalogFileName}, &stdout, &stderr); code != 2 {
		t.Fatalf("both flags exit=%d want 2", code)
	}
}

func TestUnit_Run_StdoutExport(t *testing.T) {
	t.Parallel()
	want, err := marshalCanonical(buildExport(provider.BuiltInCapabilityCatalog()))
	if err != nil {
		t.Fatal(err)
	}
	var stdout, stderr bytes.Buffer
	if code := run(nil, &stdout, &stderr); code != 0 {
		t.Fatalf("stdout export exit=%d stderr=%s", code, stderr.String())
	}
	if !bytes.Equal(normalizeNewline(stdout.Bytes()), normalizeNewline(want)) {
		t.Fatalf("stdout export mismatch")
	}
}

func TestUnit_Run_StdoutWriteFailures(t *testing.T) {
	t.Parallel()
	var stderr bytes.Buffer
	if code := run(nil, shortWriter{}, &stderr); code != 2 {
		t.Fatalf("short write exit=%d want 2 stderr=%s", code, stderr.String())
	}
	stderr.Reset()
	if code := run(nil, errWriter{}, &stderr); code != 2 {
		t.Fatalf("error write exit=%d want 2 stderr=%s", code, stderr.String())
	}
}

func TestUnit_Main_UsesExitFunc(t *testing.T) {
	prev := exitFunc
	var got int
	exitFunc = func(code int) { got = code }
	t.Cleanup(func() { exitFunc = prev })
	// main() reads os.Args; run with default args via replacing - use run path instead.
	// Cover main by invoking it after setting Args to a known-good stdout export.
	oldArgs := os.Args
	os.Args = []string{"export_capabilities"}
	t.Cleanup(func() { os.Args = oldArgs })
	main()
	if got != 0 {
		t.Fatalf("main exit=%d want 0", got)
	}
}
