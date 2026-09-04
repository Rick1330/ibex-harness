package main

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

type stubTempFile struct {
	name     string
	writeErr error
	closeErr error
}

func (s *stubTempFile) Name() string { return s.name }

func (s *stubTempFile) Write(p []byte) (int, error) {
	if s.writeErr != nil {
		return 0, s.writeErr
	}
	return len(p), nil
}

func (s *stubTempFile) Close() error { return s.closeErr }

func TestUnit_Run_WriteAtomicVerifiedByCheck(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	path := filepath.Join(dir, catalogFileName)
	var stdout, stderr bytes.Buffer
	if code := run([]string{"-o", path}, &stdout, &stderr); code != 0 {
		t.Fatalf("run -o exit=%d stderr=%s", code, stderr.String())
	}
	if code := run([]string{"-check", path}, &stdout, &stderr); code != 0 {
		t.Fatalf("post-write -check exit=%d stderr=%s", code, stderr.String())
	}
}

func TestUnit_WriteExportFile_PathError(t *testing.T) {
	t.Parallel()
	var stderr bytes.Buffer
	if code := writeExportFile("not-catalog.txt", []byte("{}"), 1, &stderr); code != 2 {
		t.Fatalf("exit=%d want 2", code)
	}
}

func TestUnit_WriteExportFile_AtomicFailure(t *testing.T) {
	prev := osCreateTemp
	t.Cleanup(func() { osCreateTemp = prev })
	osCreateTemp = func(string, string) (tempFile, error) {
		return nil, errors.New("create temp boom")
	}
	path := filepath.Join(t.TempDir(), catalogFileName)
	var stderr bytes.Buffer
	if code := writeExportFile(path, []byte("{}"), 1, &stderr); code != 2 {
		t.Fatalf("exit=%d want 2 stderr=%s", code, stderr.String())
	}
}

func TestUnit_WriteAtomic_FailureModes(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, catalogFileName)

	t.Run("createTemp", func(t *testing.T) {
		prev := osCreateTemp
		t.Cleanup(func() { osCreateTemp = prev })
		osCreateTemp = func(string, string) (tempFile, error) {
			return nil, errors.New("no temp")
		}
		if err := writeAtomic(target, []byte("x"), 0o644); err == nil {
			t.Fatal("expected createTemp error")
		}
	})

	t.Run("write", func(t *testing.T) {
		prev := osCreateTemp
		prevRm := osRemove
		removed := false
		t.Cleanup(func() {
			osCreateTemp = prev
			osRemove = prevRm
		})
		stub := &stubTempFile{name: filepath.Join(dir, "tmp-write"), writeErr: errors.New("write fail")}
		osCreateTemp = func(string, string) (tempFile, error) { return stub, nil }
		osRemove = func(string) error { removed = true; return nil }
		if err := writeAtomic(target, []byte("x"), 0o644); err == nil {
			t.Fatal("expected write error")
		}
		if !removed {
			t.Fatal("expected cleanup remove after write failure")
		}
	})

	t.Run("close", func(t *testing.T) {
		prev := osCreateTemp
		t.Cleanup(func() { osCreateTemp = prev })
		stub := &stubTempFile{name: filepath.Join(dir, "tmp-close"), closeErr: errors.New("close fail")}
		osCreateTemp = func(string, string) (tempFile, error) { return stub, nil }
		if err := writeAtomic(target, []byte("x"), 0o644); err == nil {
			t.Fatal("expected close error")
		}
	})

	t.Run("chmod", func(t *testing.T) {
		prevC := osCreateTemp
		prevM := osChmod
		t.Cleanup(func() {
			osCreateTemp = prevC
			osChmod = prevM
		})
		real, err := os.CreateTemp(dir, "chmod-*.tmp")
		if err != nil {
			t.Fatal(err)
		}
		name := real.Name()
		_ = real.Close()
		osCreateTemp = func(string, string) (tempFile, error) {
			return os.OpenFile(name, os.O_RDWR|os.O_TRUNC, 0o600)
		}
		osChmod = func(string, os.FileMode) error { return errors.New("chmod fail") }
		if err := writeAtomic(target, []byte("x"), 0o644); err == nil {
			t.Fatal("expected chmod error")
		}
	})

	t.Run("rename", func(t *testing.T) {
		prevC := osCreateTemp
		prevR := osRename
		t.Cleanup(func() {
			osCreateTemp = prevC
			osRename = prevR
		})
		osCreateTemp = func(dir, pattern string) (tempFile, error) {
			return os.CreateTemp(dir, pattern)
		}
		osRename = func(string, string) error { return errors.New("rename fail") }
		if err := writeAtomic(target, []byte("x"), 0o644); err == nil {
			t.Fatal("expected rename error")
		}
	})
}
