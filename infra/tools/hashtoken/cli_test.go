package main

import (
	"bytes"
	"errors"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/crypto"
)

const devSeedPAT = "ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY"

func TestRun_Success(t *testing.T) {
	t.Parallel()
	var out bytes.Buffer
	code := run([]string{devSeedPAT}, &out, ioDiscard{t}, defaultHashBearer)
	if code != 0 {
		t.Fatalf("exit code: %d", code)
	}
	hash := strings.TrimSpace(out.String())
	if !strings.HasPrefix(hash, crypto.ProductionPHCPrefix) {
		t.Fatalf("bad prefix: %q", hash)
	}
	ok, err := crypto.VerifyToken(devSeedPAT, hash, crypto.ProductionParams())
	if err != nil || !ok {
		t.Fatalf("verify: ok=%v err=%v", ok, err)
	}
}

func TestRun_EmptyToken(t *testing.T) {
	t.Parallel()
	var errBuf bytes.Buffer
	if code := run([]string{""}, ioDiscard{t}, &errBuf, defaultHashBearer); code != 2 {
		t.Fatalf("code: %d", code)
	}
}

func TestRun_NoArgs(t *testing.T) {
	t.Parallel()
	var errBuf bytes.Buffer
	if code := run(nil, ioDiscard{t}, &errBuf, defaultHashBearer); code != 2 {
		t.Fatalf("code: %d", code)
	}
}

func TestRun_TooManyArgs(t *testing.T) {
	t.Parallel()
	var errBuf bytes.Buffer
	if code := run([]string{"a", "b"}, ioDiscard{t}, &errBuf, defaultHashBearer); code != 2 {
		t.Fatalf("code: %d", code)
	}
}

func TestParseArgs_TwoTokens(t *testing.T) {
	t.Parallel()
	if _, err := parseArgs([]string{"one", "two"}); err == nil {
		t.Fatal("expected error")
	}
}

func TestRun_HashError(t *testing.T) {
	t.Parallel()
	var errBuf bytes.Buffer
	hashErr := func(string) (string, error) {
		return "", errors.New("hash failed")
	}
	if code := run([]string{devSeedPAT}, ioDiscard{t}, &errBuf, hashErr); code != 2 {
		t.Fatalf("code: %d", code)
	}
}

func TestRunCLI_Success(t *testing.T) {
	t.Parallel()
	if code := runCLI([]string{devSeedPAT}); code != 0 {
		t.Fatalf("exit code: %d", code)
	}
}

type ioDiscard struct{ t *testing.T }

func (d ioDiscard) Write(p []byte) (int, error) {
	d.t.Helper()
	return len(p), nil
}
