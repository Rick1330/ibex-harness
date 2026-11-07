// Package tlscert generates throwaway ECDSA certificate chains for tests.
//
// It exists so tests can exercise TLS without committed PEM files or an
// openssl shell-out. Every artifact is written under a t.TempDir() directory
// and is removed by the testing package when the test finishes.
package tlscert

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"
)

const (
	caFile   = "ca.crt"
	certFile = "leaf.crt"
	keyFile  = "leaf.key"
)

// Options controls the generated leaf certificate. Zero values select the
// defaults documented on Generate.
type Options struct {
	// DNSNames and IPAddresses are the leaf Subject Alternative Names. When
	// both are empty and NoSAN is false, the helper uses DNS:localhost plus
	// IP:127.0.0.1 and IP:::1, which covers every loopback test dial.
	DNSNames    []string
	IPAddresses []net.IP
	// NoSAN forces a leaf with no Subject Alternative Name at all. It is the
	// fixture for the CN-only rejection path; it cannot be combined with
	// DNSNames or IPAddresses.
	NoSAN bool
	// NotBefore and NotAfter bound the leaf validity. Zero values default to
	// one hour before now and 24 hours after now.
	NotBefore time.Time
	NotAfter  time.Time
}

// Pair is the on-disk result of Generate. CAPool contains the CA certificate
// and is ready to use as tls.Config.RootCAs.
type Pair struct {
	CAFile   string
	CertFile string
	KeyFile  string
	CAPEM    []byte
	CertPEM  []byte
	KeyPEM   []byte
	CAPool   *x509.CertPool
}

// Generate creates a self-signed CA and one server leaf signed by it, then
// writes ca.crt, leaf.crt, and leaf.key (mode 0600) into dir. An empty dir
// selects t.TempDir(). The CA private key is not returned: callers only ever
// need the CA certificate to verify the leaf.
func Generate(t *testing.T, dir string, opts Options) Pair {
	t.Helper()
	if dir == "" {
		dir = t.TempDir()
	}
	if opts.NoSAN {
		requireNoSANEntries(t, opts)
	}
	applyDefaults(t, &opts)

	caCert, caKey := newCA(t)
	leafCert, leafKey := newLeaf(t, caCert, caKey, opts)

	caPEM := encodeCertificate(t, caCert)
	certPEM := encodeCertificate(t, leafCert)
	keyPEM := encodeKey(t, leafKey)

	caPath := filepath.Join(dir, caFile)
	certPath := filepath.Join(dir, certFile)
	keyPath := filepath.Join(dir, keyFile)
	writeFile(t, caPath, caPEM, 0o644)
	writeFile(t, certPath, certPEM, 0o644)
	writeFile(t, keyPath, keyPEM, 0o600)

	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(caPEM) {
		t.Fatalf("tlscert: generated CA does not parse")
	}
	return Pair{
		CAFile: caPath, CertFile: certPath, KeyFile: keyPath,
		CAPEM: caPEM, CertPEM: certPEM, KeyPEM: keyPEM, CAPool: pool,
	}
}

// requireNoSANEntries keeps the NoSAN/SAN conflict check out of Generate so
// each conditional stays single-branch for Code Health.
func requireNoSANEntries(t *testing.T, opts Options) {
	t.Helper()
	if len(opts.DNSNames) > 0 {
		t.Fatalf("tlscert: NoSAN cannot be combined with SAN entries")
	}
	if len(opts.IPAddresses) > 0 {
		t.Fatalf("tlscert: NoSAN cannot be combined with SAN entries")
	}
}

// applySANDefaults mirrors the two SAN inputs into the same default only when
// the caller supplied neither; early returns keep each branch single.
func applySANDefaults(opts *Options) {
	if opts.NoSAN {
		return
	}
	if len(opts.DNSNames) > 0 {
		return
	}
	if len(opts.IPAddresses) > 0 {
		return
	}
	opts.DNSNames = []string{"localhost"}
	opts.IPAddresses = []net.IP{net.ParseIP("127.0.0.1"), net.ParseIP("::1")}
}

func applyDefaults(t *testing.T, opts *Options) {
	t.Helper()
	applySANDefaults(opts)
	now := time.Now()
	if opts.NotBefore.IsZero() {
		opts.NotBefore = now.Add(-time.Hour)
	}
	if opts.NotAfter.IsZero() {
		opts.NotAfter = now.Add(24 * time.Hour)
	}
}

func newCA(t *testing.T) (*x509.Certificate, *ecdsa.PrivateKey) {
	t.Helper()
	key := newKey(t)
	template := &x509.Certificate{
		SerialNumber:          newSerial(t),
		Subject:               pkix.Name{CommonName: "IBEX test CA"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(10 * 365 * 24 * time.Hour),
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageCRLSign | x509.KeyUsageDigitalSignature,
		BasicConstraintsValid: true,
		IsCA:                  true,
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatalf("tlscert: create CA certificate: %v", err)
	}
	cert, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatalf("tlscert: parse CA certificate: %v", err)
	}
	return cert, key
}

func newLeaf(t *testing.T, ca *x509.Certificate, caKey *ecdsa.PrivateKey, opts Options) (*x509.Certificate, *ecdsa.PrivateKey) {
	t.Helper()
	key := newKey(t)
	template := &x509.Certificate{
		SerialNumber:          newSerial(t),
		Subject:               pkix.Name{CommonName: "ibex-test-leaf"},
		NotBefore:             opts.NotBefore,
		NotAfter:              opts.NotAfter,
		KeyUsage:              x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
		IsCA:                  false,
		DNSNames:              opts.DNSNames,
		IPAddresses:           opts.IPAddresses,
	}
	der, err := x509.CreateCertificate(rand.Reader, template, ca, &key.PublicKey, caKey)
	if err != nil {
		t.Fatalf("tlscert: create leaf certificate: %v", err)
	}
	cert, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatalf("tlscert: parse leaf certificate: %v", err)
	}
	return cert, key
}

func newKey(t *testing.T) *ecdsa.PrivateKey {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("tlscert: generate key: %v", err)
	}
	return key
}

func newSerial(t *testing.T) *big.Int {
	t.Helper()
	serial, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	if err != nil {
		t.Fatalf("tlscert: generate serial: %v", err)
	}
	return serial
}

func encodeCertificate(t *testing.T, cert *x509.Certificate) []byte {
	t.Helper()
	return pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: cert.Raw})
}

func encodeKey(t *testing.T, key *ecdsa.PrivateKey) []byte {
	t.Helper()
	der, err := x509.MarshalECPrivateKey(key)
	if err != nil {
		t.Fatalf("tlscert: marshal private key: %v", err)
	}
	return pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: der})
}

func writeFile(t *testing.T, path string, data []byte, mode os.FileMode) {
	t.Helper()
	if err := os.WriteFile(path, data, mode); err != nil {
		t.Fatalf("tlscert: write %s: %v", path, err)
	}
}
