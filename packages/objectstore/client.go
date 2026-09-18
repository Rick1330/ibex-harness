// Package objectstore provides encrypted S3-compatible Put/Delete for session archives (4.P.3).
package objectstore

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/google/uuid"
)

const (
	defaultRegion = "us-east-1"
	defaultBucket = "ibex-sessions"
	defaultKeyID  = "v1"
	s3URIScheme   = "s3://"
)

// Credentials holds S3 access identity (avoids bare string triples).
type Credentials struct {
	AccessKey string
	SecretKey string
}

func (c Credentials) valid() bool {
	return c.AccessKey != "" && c.SecretKey != ""
}

// ObjectKey is a bucket-relative object path.
type ObjectKey string

func (k ObjectKey) String() string { return string(k) }

func (k ObjectKey) normalized() ObjectKey {
	return ObjectKey(strings.TrimLeft(string(k), "/"))
}

func (k ObjectKey) empty() bool { return k.normalized() == "" }

// ObjectURI is an s3://bucket/key reference.
type ObjectURI string

func (u ObjectURI) String() string { return string(u) }

func parseObjectURI(raw string) (bucket string, key ObjectKey, err error) {
	if !strings.HasPrefix(raw, s3URIScheme) {
		return "", "", fmt.Errorf("objectstore: unsupported uri %q", raw)
	}
	rest := strings.TrimPrefix(raw, s3URIScheme)
	slash := strings.IndexByte(rest, '/')
	if slash < 1 {
		return "", "", fmt.Errorf("objectstore: malformed uri %q", raw)
	}
	return rest[:slash], ObjectKey(rest[slash+1:]), nil
}

// Config holds S3-compatible endpoint settings.
type Config struct {
	Endpoint string
	Creds    Credentials
	Bucket   string
	Region   string
	KeyID    string
	// AllowInsecureHTTP permits cleartext http:// endpoints (local MinIO / tests only).
	AllowInsecureHTTP bool
}

// ConfigFromEnv loads S3_* / MinIO-compatible settings.
func ConfigFromEnv() Config {
	region := os.Getenv("S3_REGION")
	if region == "" {
		region = defaultRegion
	}
	bucket := os.Getenv("S3_BUCKET_SESSIONS")
	if bucket == "" {
		bucket = defaultBucket
	}
	keyID := os.Getenv("S3_ENCRYPTION_KEY_ID")
	if keyID == "" {
		keyID = defaultKeyID
	}
	insecure := os.Getenv("S3_ALLOW_INSECURE_HTTP")
	return Config{
		Endpoint: strings.TrimRight(os.Getenv("S3_ENDPOINT"), "/"),
		Creds: Credentials{
			AccessKey: os.Getenv("S3_ACCESS_KEY"),
			SecretKey: os.Getenv("S3_SECRET_KEY"),
		},
		Bucket:            bucket,
		Region:            region,
		KeyID:             keyID,
		AllowInsecureHTTP: insecure == "1" || strings.EqualFold(insecure, "true"),
	}
}

// Client is a minimal path-style S3 client (MinIO-compatible).
type Client struct {
	cfg    Config
	http   *http.Client
	master crypto.MasterKey
	signer *awsV4Signer
}

// New creates a client. masterKeyB64 must be 32-byte base64 KEK for Seal.
func New(cfg Config, masterKeyB64 string, httpClient *http.Client) (*Client, error) {
	if cfg.Endpoint == "" {
		return nil, fmt.Errorf("objectstore: S3_ENDPOINT required")
	}
	if err := validateEndpoint(cfg); err != nil {
		return nil, err
	}
	if !cfg.Creds.valid() {
		return nil, fmt.Errorf("objectstore: S3 credentials required")
	}
	master, err := crypto.ParseMasterKeyBase64(masterKeyB64)
	if err != nil {
		return nil, fmt.Errorf("objectstore: master key: %w", err)
	}
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 30 * time.Second}
	}
	httpClient = withNoRedirectClient(httpClient)
	if cfg.Region == "" {
		cfg.Region = defaultRegion
	}
	if cfg.KeyID == "" {
		cfg.KeyID = defaultKeyID
	}
	return &Client{
		cfg:    cfg,
		http:   httpClient,
		master: master,
		signer: newAWSV4Signer(cfg.Creds, cfg.Region),
	}, nil
}

func validateEndpoint(cfg Config) error {
	u, err := url.Parse(cfg.Endpoint)
	if err != nil {
		return fmt.Errorf("objectstore: endpoint: %w", err)
	}
	if u.Host == "" {
		return fmt.Errorf("objectstore: endpoint host required")
	}
	if u.RawQuery != "" || u.Fragment != "" {
		return fmt.Errorf("objectstore: endpoint must not include query or fragment")
	}
	switch strings.ToLower(u.Scheme) {
	case "https":
		return nil
	case "http":
		if cfg.AllowInsecureHTTP {
			return nil
		}
		return fmt.Errorf("objectstore: HTTPS required (set AllowInsecureHTTP for local MinIO)")
	default:
		return fmt.Errorf("objectstore: endpoint scheme must be https (or http with AllowInsecureHTTP)")
	}
}

// withNoRedirectClient refuses redirects: SigV4 signatures bind host/path/query
// and cannot be safely reused on a redirected URL without re-signing.
func withNoRedirectClient(base *http.Client) *http.Client {
	out := *base
	out.CheckRedirect = func(_ *http.Request, _ []*http.Request) error {
		return errors.New("objectstore: redirects not followed (re-sign required)")
	}
	return &out
}

// ArchivedBlob is the on-wire envelope stored in object storage.
type ArchivedBlob struct {
	CiphertextB64 string `json:"ciphertext_b64"`
	WrappedDEKB64 string `json:"wrapped_dek_b64"`
	KeyID         string `json:"key_id"`
}

// PutEncrypted seals plaintext and puts JSON envelope under key.
// Returns s3://bucket/key URI for archived_to.
func (c *Client) PutEncrypted(ctx context.Context, key ObjectKey, plaintext []byte) (ObjectURI, error) {
	if key.empty() {
		return "", fmt.Errorf("objectstore: key required")
	}
	sealed, err := crypto.Seal(c.master, c.cfg.KeyID, plaintext)
	if err != nil {
		return "", err
	}
	body, err := json.Marshal(ArchivedBlob{
		CiphertextB64: base64.StdEncoding.EncodeToString(sealed.Ciphertext),
		WrappedDEKB64: base64.StdEncoding.EncodeToString(sealed.WrappedDEK),
		KeyID:         sealed.KeyID,
	})
	if err != nil {
		return "", err
	}
	nk := key.normalized()
	if err := c.putObject(ctx, nk, body, "application/json"); err != nil {
		return "", err
	}
	return ObjectURI(fmt.Sprintf("%s%s/%s", s3URIScheme, c.cfg.Bucket, nk)), nil
}

// OrgPrefix returns the key prefix for an org's archived sessions.
func OrgPrefix(orgID uuid.UUID) ObjectKey {
	return ObjectKey(orgID.String() + "/")
}

// DeletePrefix deletes all objects under the org prefix.
func (c *Client) DeletePrefix(ctx context.Context, orgID uuid.UUID) error {
	keys, err := c.listKeys(ctx, OrgPrefix(orgID))
	if err != nil {
		return err
	}
	for _, k := range keys {
		if err := c.deleteObject(ctx, k); err != nil {
			return err
		}
	}
	return nil
}

// DeleteURI deletes a single s3://bucket/key object (bucket must match config).
func (c *Client) DeleteURI(ctx context.Context, uri ObjectURI) error {
	bucket, key, err := parseObjectURI(uri.String())
	if err != nil {
		return err
	}
	if bucket != c.cfg.Bucket {
		return fmt.Errorf("objectstore: bucket mismatch")
	}
	if key.empty() {
		return fmt.Errorf("objectstore: key required")
	}
	return c.deleteObject(ctx, key)
}

func (c *Client) putObject(ctx context.Context, key ObjectKey, body []byte, contentType string) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, c.objectURL(key), bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", contentType)
	req.Header.Set("Content-Length", fmt.Sprintf("%d", len(body)))
	if err := c.signer.sign(ctx, req); err != nil {
		return err
	}
	return c.doExpectOK(req, key.String(), true)
}

func (c *Client) deleteObject(ctx context.Context, key ObjectKey) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, c.objectURL(key), nil)
	if err != nil {
		return err
	}
	if err := c.signer.sign(ctx, req); err != nil {
		return err
	}
	return c.doExpectOK(req, key.String(), false)
}

func (c *Client) doExpectOK(req *http.Request, key string, failNotFound bool) error {
	resp, err := c.http.Do(req)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode < 300 {
		return nil
	}
	if !failNotFound && resp.StatusCode == http.StatusNotFound {
		return nil
	}
	b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
	return fmt.Errorf("objectstore: %s %s: %s %s", req.Method, key, resp.Status, string(b))
}

func (c *Client) listKeys(ctx context.Context, prefix ObjectKey) ([]ObjectKey, error) {
	var out []ObjectKey
	token := ""
	for {
		page, next, err := c.listPage(ctx, prefix, token)
		if err != nil {
			return nil, err
		}
		out = append(out, page...)
		if next == "" {
			return out, nil
		}
		token = next
	}
}

func (c *Client) listPage(ctx context.Context, prefix ObjectKey, continuation string) ([]ObjectKey, string, error) {
	u, err := url.Parse(c.bucketURL())
	if err != nil {
		return nil, "", err
	}
	q := u.Query()
	q.Set("list-type", "2")
	q.Set("prefix", prefix.String())
	if continuation != "" {
		q.Set("continuation-token", continuation)
	}
	// Signer rewrites RawQuery with SigV4 rules (spaces as %20, not +).
	u.RawQuery = q.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, "", err
	}
	if err := c.signer.sign(ctx, req); err != nil {
		return nil, "", err
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, "", err
	}
	defer func() { _ = resp.Body.Close() }()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	if err != nil {
		return nil, "", err
	}
	if resp.StatusCode >= 300 {
		return nil, "", fmt.Errorf("objectstore: list: %s %s", resp.Status, string(body))
	}
	return parseListObjectsV2(body)
}

func (c *Client) objectURL(key ObjectKey) string {
	return c.bucketURL() + "/" + escapeKeyPath(key.normalized())
}

// escapeKeyPath percent-encodes each path segment while preserving '/' separators
// so keys containing '?', '#', or spaces do not alter the URL target.
func escapeKeyPath(key ObjectKey) string {
	parts := strings.Split(string(key), "/")
	for i, p := range parts {
		parts[i] = url.PathEscape(p)
	}
	return strings.Join(parts, "/")
}

func (c *Client) bucketURL() string {
	return c.cfg.Endpoint + "/" + c.cfg.Bucket
}
