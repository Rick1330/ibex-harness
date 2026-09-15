package sessionjwt

import (
	"crypto"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/pem"
	"fmt"
)

func parseRSAPrivateKey(pemData PrivateKeyPEM) (*rsa.PrivateKey, error) {
	block, _ := pem.Decode([]byte(pemData))
	if block == nil {
		return nil, fmt.Errorf("sessionjwt: invalid private key pem")
	}
	if key, err := x509.ParsePKCS1PrivateKey(block.Bytes); err == nil {
		return key, nil
	}
	parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("sessionjwt: parse private key: %w", err)
	}
	key, ok := parsed.(*rsa.PrivateKey)
	if !ok {
		return nil, fmt.Errorf("sessionjwt: not an RSA private key")
	}
	return key, nil
}

func parseRSAPublicKeys(pemData PublicKeysPEM) ([]*rsa.PublicKey, error) {
	var keys []*rsa.PublicKey
	rest := []byte(pemData)
	for {
		var block *pem.Block
		block, rest = pem.Decode(rest)
		if block == nil {
			break
		}
		key, err := parseRSAPublicKeyBlock(block)
		if err != nil {
			return nil, err
		}
		if key != nil {
			keys = append(keys, key)
		}
	}
	return keys, nil
}

func parseRSAPublicKeyBlock(block *pem.Block) (*rsa.PublicKey, error) {
	pub, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err == nil {
		rsaPub, ok := pub.(*rsa.PublicKey)
		if !ok {
			return nil, fmt.Errorf("sessionjwt: not an RSA public key")
		}
		return rsaPub, nil
	}
	cert, cerr := x509.ParseCertificate(block.Bytes)
	if cerr != nil {
		return nil, fmt.Errorf("sessionjwt: parse public key: %w", err)
	}
	rsaPub, ok := cert.PublicKey.(*rsa.PublicKey)
	if !ok {
		return nil, nil
	}
	return rsaPub, nil
}

func b64(b []byte) string {
	return rawURLEncode(b)
}

func b64dec(s string) ([]byte, error) {
	return rawURLDecode(s)
}

func verifyPKCS1(key *rsa.PublicKey, sum, sig []byte) error {
	// JWT RS256 (RFC 7518) requires PKCS#1 v1.5 verification.
	return rsa.VerifyPKCS1v15(key, crypto.SHA256, sum, sig) // NOSONAR
}

func sha256Sum(body string) [32]byte {
	return sha256.Sum256([]byte(body))
}
