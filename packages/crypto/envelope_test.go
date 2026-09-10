package crypto

import (
	"bytes"
	"encoding/base64"
	"testing"
)

func testMaster(t *testing.T) MasterKey {
	t.Helper()
	raw := GenerateRandomBytes(MasterKeySize)
	var mk MasterKey
	copy(mk[:], raw)
	return mk
}

func TestEnvelope_RoundTrip(t *testing.T) {
	mk := testMaster(t)
	plain := []byte("sk-test-provider-secret")
	sealed, err := Seal(mk, "v1", plain)
	if err != nil {
		t.Fatalf("Seal: %v", err)
	}
	if sealed.KeyID != "v1" {
		t.Fatalf("KeyID=%q", sealed.KeyID)
	}
	if len(sealed.Ciphertext) <= NonceSizeGCM || len(sealed.WrappedDEK) <= NonceSizeGCM {
		t.Fatalf("blobs too short: ct=%d wrap=%d", len(sealed.Ciphertext), len(sealed.WrappedDEK))
	}
	got, err := Open(mk, sealed)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	if !bytes.Equal(got, plain) {
		t.Fatalf("plaintext mismatch")
	}
}

func TestEnvelope_DistinctNonces(t *testing.T) {
	mk := testMaster(t)
	plain := []byte("same-plaintext")
	a, err := Seal(mk, "v1", plain)
	if err != nil {
		t.Fatal(err)
	}
	b, err := Seal(mk, "v1", plain)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Equal(a.Ciphertext, b.Ciphertext) {
		t.Fatal("ciphertext nonces/blobs must differ across seals")
	}
	if bytes.Equal(a.WrappedDEK, b.WrappedDEK) {
		t.Fatal("wrapped DEK nonces/blobs must differ across seals")
	}
}

func TestEnvelope_TamperRejected(t *testing.T) {
	mk := testMaster(t)
	sealed, err := Seal(mk, "v1", []byte("secret"))
	if err != nil {
		t.Fatal(err)
	}
	sealed.Ciphertext[len(sealed.Ciphertext)-1] ^= 0xff
	if _, err := Open(mk, sealed); err == nil {
		t.Fatal("expected open failure on tampered ciphertext")
	}
}

func TestEnvelope_WrongKeyRejected(t *testing.T) {
	mk := testMaster(t)
	sealed, err := Seal(mk, "v1", []byte("secret"))
	if err != nil {
		t.Fatal(err)
	}
	other := testMaster(t)
	if _, err := Open(other, sealed); err == nil {
		t.Fatal("expected open failure with wrong master key")
	}
}

func TestParseMasterKeyBase64(t *testing.T) {
	raw := GenerateRandomBytes(MasterKeySize)
	enc := base64.StdEncoding.EncodeToString(raw)
	mk, err := ParseMasterKeyBase64(enc)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(mk[:], raw) {
		t.Fatal("decoded key mismatch")
	}
	if _, err := ParseMasterKeyBase64("not-base64!!"); err == nil {
		t.Fatal("expected parse error")
	}
	if _, err := ParseMasterKeyBase64(base64.StdEncoding.EncodeToString([]byte("short"))); err == nil {
		t.Fatal("expected length error")
	}
}

func TestSeal_RequiresKeyID(t *testing.T) {
	mk := testMaster(t)
	if _, err := Seal(mk, "", []byte("x")); err == nil {
		t.Fatal("expected key id required")
	}
}
