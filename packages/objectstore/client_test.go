package objectstore

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/crypto"
	"github.com/google/uuid"
)

func testMasterB64(t *testing.T) string {
	t.Helper()
	master := make([]byte, 32)
	for i := range master {
		master[i] = byte(i + 1)
	}
	return base64.StdEncoding.EncodeToString(master)
}

func testCfg(endpoint string) Config {
	return Config{
		Endpoint:          endpoint,
		Creds:             Credentials{AccessKey: "minioadmin", SecretKey: "minioadmin"},
		Bucket:            "ibex-sessions",
		Region:            "us-east-1",
		KeyID:             "v1",
		AllowInsecureHTTP: true,
	}
}

func mustNew(t *testing.T, cfg Config, httpClient *http.Client) *Client {
	t.Helper()
	client, err := New(cfg, testMasterB64(t), httpClient)
	if err != nil {
		t.Fatal(err)
	}
	return client
}

func newTestServerClient(t *testing.T, h http.HandlerFunc) (*Client, *httptest.Server) {
	t.Helper()
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	return mustNew(t, testCfg(srv.URL), srv.Client()), srv
}

func writeFixture(w http.ResponseWriter, body string) {
	// Test-only S3/XML fixtures (not HTML). Codacy XSS rule flags ResponseWriter.Write.
	// nosemgrep: go.lang.security.audit.xss.no-direct-write-to-responsewriter
	_, _ = io.Copy(w, strings.NewReader(body))
}

func statusHandler(code int, body string) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/octet-stream")
		w.WriteHeader(code)
		if body != "" {
			writeFixture(w, body)
		}
	}
}

func TestNew_Validation(t *testing.T) {
	t.Parallel()
	mk := testMasterB64(t)
	if _, err := New(Config{}, mk, nil); err == nil {
		t.Fatal("expected endpoint error")
	}
	cfg := testCfg("http://127.0.0.1:9")
	cfg.Creds = Credentials{}
	if _, err := New(cfg, mk, nil); err == nil {
		t.Fatal("expected creds error")
	}
	if _, err := New(testCfg("http://127.0.0.1:9"), "not-b64", nil); err == nil {
		t.Fatal("expected master key error")
	}
}

func TestNew_RejectsHTTPUnlessAllowed(t *testing.T) {
	t.Parallel()
	mk := testMasterB64(t)
	cfg := testCfg("http://minio.example:9000")
	cfg.AllowInsecureHTTP = false
	if _, err := New(cfg, mk, nil); err == nil || !strings.Contains(err.Error(), "HTTPS required") {
		t.Fatalf("expected HTTPS required, got %v", err)
	}
	cfg.AllowInsecureHTTP = true
	if _, err := New(cfg, mk, nil); err != nil {
		t.Fatal(err)
	}
	httpsCfg := testCfg("https://s3.example.com")
	httpsCfg.AllowInsecureHTTP = false
	if _, err := New(httpsCfg, mk, nil); err != nil {
		t.Fatal(err)
	}
}

func TestNew_RejectsEndpointWithoutHost(t *testing.T) {
	t.Parallel()
	mk := testMasterB64(t)
	cfg := testCfg("https://")
	if _, err := New(cfg, mk, nil); err == nil || !strings.Contains(err.Error(), "host") {
		t.Fatalf("expected host error, got %v", err)
	}
	cfg = testCfg("https://s3.example.com?x=1")
	if _, err := New(cfg, mk, nil); err == nil || !strings.Contains(err.Error(), "query") {
		t.Fatalf("expected query error, got %v", err)
	}
}

func TestCheckRedirect_RefusesAllRedirects(t *testing.T) {
	t.Parallel()
	client := mustNew(t, testCfg("https://s3.example.com"), nil)
	httpsReq := &http.Request{
		Method: http.MethodGet,
		URL:    &url.URL{Scheme: "https", Host: "s3.example.com", Path: "/bucket"},
	}
	nextReq := &http.Request{
		Method: http.MethodGet,
		URL:    &url.URL{Scheme: "https", Host: "s3.example.com", Path: "/other"},
	}
	if err := client.http.CheckRedirect(nextReq, []*http.Request{httpsReq}); err == nil {
		t.Fatal("expected redirect rejection")
	}
}

func TestPutEncrypted_RoundTripSeal(t *testing.T) {
	t.Parallel()
	const plaintext = "secret-payload"
	var putBody []byte
	var putPath string
	client, _ := newTestServerClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPut {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		putPath = r.URL.Path
		var err error
		putBody, err = io.ReadAll(r.Body)
		if err != nil {
			t.Errorf("read body: %v", err)
		}
		w.WriteHeader(http.StatusOK)
	})

	uri, err := client.PutEncrypted(context.Background(), ObjectKey("org/a.json"), []byte(plaintext))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(uri.String(), "s3://ibex-sessions/") || !strings.Contains(uri.String(), "org/a.json") {
		t.Fatalf("uri=%s", uri)
	}
	if !strings.Contains(putPath, "org/a.json") {
		t.Fatalf("put path=%s", putPath)
	}
	assertArchivedPlaintext(t, putBody, plaintext)
}

func assertArchivedPlaintext(t *testing.T, putBody []byte, want string) {
	t.Helper()
	if len(putBody) == 0 {
		t.Fatal("empty body")
	}
	var blob ArchivedBlob
	if err := json.Unmarshal(putBody, &blob); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	ct, err := base64.StdEncoding.DecodeString(blob.CiphertextB64)
	if err != nil {
		t.Fatal(err)
	}
	wrapped, err := base64.StdEncoding.DecodeString(blob.WrappedDEKB64)
	if err != nil {
		t.Fatal(err)
	}
	mk, err := crypto.ParseMasterKeyBase64(testMasterB64(t))
	if err != nil {
		t.Fatal(err)
	}
	plain, err := crypto.Open(mk, crypto.SealedBlob{
		Ciphertext: ct,
		WrappedDEK: wrapped,
		KeyID:      blob.KeyID,
	})
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if string(plain) != want {
		t.Fatalf("plain=%q want=%q", plain, want)
	}
}

func TestPutEncrypted_EmptyKey(t *testing.T) {
	t.Parallel()
	client, _ := newTestServerClient(t, statusHandler(http.StatusOK, ""))
	_, err := client.PutEncrypted(context.Background(), ObjectKey(""), []byte("x"))
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestObjectURL_EscapesPathSegments(t *testing.T) {
	t.Parallel()
	client := mustNew(t, testCfg("http://127.0.0.1:9"), nil)
	got := client.objectURL(ObjectKey("org/a b?x#y.json"))
	if !strings.Contains(got, "/org/") {
		t.Fatalf("lost separator: %s", got)
	}
	if strings.Contains(got, "?") || strings.Contains(got, "#") {
		t.Fatalf("unescaped reserved chars: %s", got)
	}
	u, err := url.Parse(got)
	if err != nil {
		t.Fatal(err)
	}
	// Path is unescaped by Parse; ensure segments round-trip.
	if !strings.Contains(u.Path, "a b") || !strings.Contains(u.EscapedPath(), "%3F") {
		t.Fatalf("path=%q escaped=%q", u.Path, u.EscapedPath())
	}
}

func TestOrgPrefix(t *testing.T) {
	t.Parallel()
	id := uuid.MustParse("22222222-2222-2222-2222-222222222222")
	if got := OrgPrefix(id); got != ObjectKey(id.String()+"/") {
		t.Fatalf("got %s", got)
	}
}

func TestDeleteURI_Errors(t *testing.T) {
	t.Parallel()
	client := mustNew(t, testCfg("http://127.0.0.1:9"), nil)
	for _, u := range []ObjectURI{"http://x", "s3://onlybucket", "s3://other/key"} {
		if err := client.DeleteURI(context.Background(), u); err == nil {
			t.Fatalf("expected error for %s", u)
		}
	}
}

func TestDeleteURI_NotFoundOK(t *testing.T) {
	t.Parallel()
	client, _ := newTestServerClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodDelete {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	if err := client.DeleteURI(context.Background(), ObjectURI("s3://ibex-sessions/missing")); err != nil {
		t.Fatal(err)
	}
}

func TestDeletePrefix_ListsAndDeletes(t *testing.T) {
	t.Parallel()
	deleted := map[string]bool{}
	client, _ := newTestServerClient(t, func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && strings.Contains(r.URL.RawQuery, "list-type=2"):
			w.Header().Set("Content-Type", "application/xml")
			writeFixture(w, `<?xml version="1.0"?>
<ListBucketResult>
  <Contents><Key>org/a</Key></Contents>
  <Contents><Key>org/b</Key></Contents>
  <IsTruncated>false</IsTruncated>
</ListBucketResult>`)
		case r.Method == http.MethodDelete:
			deleted[r.URL.Path] = true
			w.WriteHeader(http.StatusNoContent)
		default:
			w.WriteHeader(http.StatusOK)
		}
	})
	org := uuid.MustParse("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
	if err := client.DeletePrefix(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	if len(deleted) != 2 {
		t.Fatalf("deleted=%v", deleted)
	}
}

func TestParseListObjectsV2_Truncated(t *testing.T) {
	t.Parallel()
	body := []byte(`<?xml version="1.0"?>
<ListBucketResult>
  <Contents><Key>k1</Key></Contents>
  <IsTruncated>true</IsTruncated>
  <NextContinuationToken>tok</NextContinuationToken>
</ListBucketResult>`)
	keys, next, err := parseListObjectsV2(body)
	if err != nil {
		t.Fatal(err)
	}
	if next != "tok" {
		t.Fatalf("next=%q", next)
	}
	if len(keys) != 1 || keys[0] != "k1" {
		t.Fatalf("keys=%v", keys)
	}
}

func TestParseListObjectsV2_BadXML(t *testing.T) {
	t.Parallel()
	_, _, err := parseListObjectsV2([]byte(`<not`))
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestConfigFromEnv_Defaults(t *testing.T) {
	t.Setenv("S3_ENDPOINT", "http://localhost:9000/")
	t.Setenv("S3_ACCESS_KEY", "a")
	t.Setenv("S3_SECRET_KEY", "b")
	t.Setenv("S3_REGION", "")
	t.Setenv("S3_BUCKET_SESSIONS", "")
	t.Setenv("S3_ENCRYPTION_KEY_ID", "")
	t.Setenv("S3_ALLOW_INSECURE_HTTP", "true")
	cfg := ConfigFromEnv()
	if cfg.Endpoint != "http://localhost:9000" {
		t.Fatalf("endpoint=%q", cfg.Endpoint)
	}
	if cfg.Bucket != defaultBucket || cfg.Region != defaultRegion {
		t.Fatalf("%+v", cfg)
	}
	if !cfg.AllowInsecureHTTP {
		t.Fatal("expected AllowInsecureHTTP from env")
	}
}

func TestPutObject_HTTPError(t *testing.T) {
	t.Parallel()
	client, _ := newTestServerClient(t, statusHandler(http.StatusForbidden, "nope"))
	_, err := client.PutEncrypted(context.Background(), ObjectKey("x"), []byte("y"))
	if err == nil || !strings.Contains(err.Error(), "403") {
		t.Fatalf("err=%v", err)
	}
}

func TestListKeys_PaginationAndListError(t *testing.T) {
	t.Parallel()
	calls := 0
	client, _ := newTestServerClient(t, func(w http.ResponseWriter, r *http.Request) {
		calls++
		w.Header().Set("Content-Type", "application/xml")
		if calls == 1 {
			writeFixture(w, `<?xml version="1.0"?>
<ListBucketResult>
  <Contents><Key>a</Key></Contents>
  <IsTruncated>true</IsTruncated>
  <NextContinuationToken>n1</NextContinuationToken>
</ListBucketResult>`)
			return
		}
		writeFixture(w, `<?xml version="1.0"?>
<ListBucketResult>
  <Contents><Key>b</Key></Contents>
  <IsTruncated>false</IsTruncated>
</ListBucketResult>`)
	})
	keys, err := client.listKeys(context.Background(), ObjectKey("p/"))
	if err != nil {
		t.Fatal(err)
	}
	if len(keys) != 2 {
		t.Fatalf("keys=%v", keys)
	}
}

func TestListPage_HTTPError(t *testing.T) {
	t.Parallel()
	client, _ := newTestServerClient(t, statusHandler(http.StatusInternalServerError, "err"))
	_, _, err := client.listPage(context.Background(), ObjectKey("p/"), "")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestDeletePrefix_ListFailure(t *testing.T) {
	t.Parallel()
	client, _ := newTestServerClient(t, statusHandler(http.StatusBadRequest, ""))
	if err := client.DeletePrefix(context.Background(), uuid.New()); err == nil {
		t.Fatal("expected error")
	}
}

func TestHTTPDo_TransportError(t *testing.T) {
	t.Parallel()
	client := mustNew(t, testCfg("http://127.0.0.1:9"), &http.Client{
		Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
			return nil, context.Canceled
		}),
	})
	if err := client.deleteObject(context.Background(), ObjectKey("x")); err == nil {
		t.Fatal("expected transport error")
	}
	_, _, err := client.listPage(context.Background(), ObjectKey("p/"), "tok")
	if err == nil {
		t.Fatal("expected list transport error")
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestPutEncrypted_EmptyKeyIDFailsSeal(t *testing.T) {
	t.Parallel()
	client, _ := newTestServerClient(t, statusHandler(http.StatusOK, ""))
	client.cfg.KeyID = ""
	_, err := client.PutEncrypted(context.Background(), ObjectKey("x"), []byte("y"))
	if err == nil {
		t.Fatal("expected seal error")
	}
}

func TestDeletePrefix_DeleteFailure(t *testing.T) {
	t.Parallel()
	client, _ := newTestServerClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			w.Header().Set("Content-Type", "application/xml")
			writeFixture(w, `<?xml version="1.0"?><ListBucketResult>
  <Contents><Key>x</Key></Contents><IsTruncated>false</IsTruncated>
</ListBucketResult>`)
			return
		}
		w.WriteHeader(http.StatusInternalServerError)
	})
	if err := client.DeletePrefix(context.Background(), uuid.New()); err == nil {
		t.Fatal("expected error")
	}
}

func TestListPage_BadXML(t *testing.T) {
	t.Parallel()
	client, _ := newTestServerClient(t, statusHandler(http.StatusOK, "not-xml"))
	_, _, err := client.listPage(context.Background(), ObjectKey("p/"), "")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestListPage_SignsQueryWithSpaces(t *testing.T) {
	t.Parallel()
	var rawQuery string
	client, _ := newTestServerClient(t, func(w http.ResponseWriter, r *http.Request) {
		rawQuery = r.URL.RawQuery
		w.Header().Set("Content-Type", "application/xml")
		writeFixture(w, `<?xml version="1.0"?><ListBucketResult><IsTruncated>false</IsTruncated></ListBucketResult>`)
	})
	_, _, err := client.listPage(context.Background(), ObjectKey("p with space/"), "")
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(rawQuery, "+") {
		t.Fatalf("SigV4 query must use %%20 not +: %s", rawQuery)
	}
	if !strings.Contains(rawQuery, "%20") {
		t.Fatalf("expected escaped space in query: %s", rawQuery)
	}
}
