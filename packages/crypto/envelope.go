package crypto

import (
	"crypto/aes"
	"crypto/cipher"
	"encoding/base64"
	"errors"
	"fmt"
)

const (
	// NonceSizeGCM is the AES-256-GCM nonce length (96 bits) required by ADR-0010.
	NonceSizeGCM = 12
	// DEKSize is the data-encryption key length (AES-256).
	DEKSize = 32
	// MasterKeySize is the local KEK length.
	MasterKeySize = 32
)

var (
	// ErrInvalidMasterKey indicates the KEK is the wrong length or unparsable.
	ErrInvalidMasterKey = errors.New("crypto: master key must be 32 bytes")
	// ErrInvalidSealedBlob indicates ciphertext or wrapped DEK is truncated/corrupt.
	ErrInvalidSealedBlob = errors.New("crypto: invalid sealed blob")
	// ErrOpenFailed indicates GCM authentication failed (tamper or wrong key).
	ErrOpenFailed = errors.New("crypto: open failed")
)

// MasterKey is a 32-byte AES-256 key-encryption key (KEK).
type MasterKey [MasterKeySize]byte

// SealedBlob is the envelope payload stored at rest (nonce||ciphertext columns).
type SealedBlob struct {
	// Ciphertext is nonce(12) || AES-GCM(DEK, plaintext) including the GCM tag.
	Ciphertext []byte
	// WrappedDEK is nonce(12) || AES-GCM(KEK, dek).
	WrappedDEK []byte
	// KeyID identifies the KEK version (e.g. "v1").
	KeyID string
}

// ParseMasterKeyBase64 decodes a standard or raw base64 32-byte master key.
func ParseMasterKeyBase64(encoded string) (MasterKey, error) {
	var out MasterKey
	if encoded == "" {
		return out, ErrInvalidMasterKey
	}
	raw, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		raw, err = base64.RawStdEncoding.DecodeString(encoded)
		if err != nil {
			return out, fmt.Errorf("%w: %v", ErrInvalidMasterKey, err)
		}
	}
	if len(raw) != MasterKeySize {
		return out, ErrInvalidMasterKey
	}
	copy(out[:], raw)
	return out, nil
}

// Seal encrypts plaintext with a fresh DEK and wraps the DEK with master.
func Seal(master MasterKey, keyID string, plaintext []byte) (SealedBlob, error) {
	if keyID == "" {
		return SealedBlob{}, fmt.Errorf("crypto: encryption key id required")
	}
	dek := GenerateRandomBytes(DEKSize)
	ct, err := gcmSeal(dek, plaintext)
	if err != nil {
		return SealedBlob{}, err
	}
	wrapped, err := gcmSeal(master[:], dek)
	if err != nil {
		return SealedBlob{}, err
	}
	return SealedBlob{
		Ciphertext: ct,
		WrappedDEK: wrapped,
		KeyID:      keyID,
	}, nil
}

// Open unwraps the DEK with master and decrypts the ciphertext.
func Open(master MasterKey, blob SealedBlob) ([]byte, error) {
	if len(blob.Ciphertext) < NonceSizeGCM+aes.BlockSize || len(blob.WrappedDEK) < NonceSizeGCM+aes.BlockSize {
		return nil, ErrInvalidSealedBlob
	}
	dek, err := gcmOpen(master[:], blob.WrappedDEK)
	if err != nil {
		return nil, ErrOpenFailed
	}
	if len(dek) != DEKSize {
		return nil, ErrInvalidSealedBlob
	}
	plain, err := gcmOpen(dek, blob.Ciphertext)
	if err != nil {
		return nil, ErrOpenFailed
	}
	return plain, nil
}

func gcmSeal(key, plaintext []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	if aead.NonceSize() != NonceSizeGCM {
		return nil, fmt.Errorf("crypto: unexpected GCM nonce size %d", aead.NonceSize())
	}
	nonce := GenerateRandomBytes(NonceSizeGCM)
	out := make([]byte, 0, NonceSizeGCM+len(plaintext)+aead.Overhead())
	out = append(out, nonce...)
	return aead.Seal(out, nonce, plaintext, nil), nil
}

func gcmOpen(key, blob []byte) ([]byte, error) {
	if len(blob) < NonceSizeGCM {
		return nil, ErrInvalidSealedBlob
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	nonce := blob[:NonceSizeGCM]
	return aead.Open(nil, nonce, blob[NonceSizeGCM:], nil)
}
