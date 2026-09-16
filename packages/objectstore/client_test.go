package objectstore

import (
	"context"
	"encoding/base64"
	"net/http"
	"net/http/httptest"
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
		Endpoint: endpoint,
		Creds:    Credentials{AccessKey: "minioadmin", SecretKey: "minioadmin"},
		Bucket:   "ibex-sessions",
		Region:   "us-east-1",
		KeyID:    "v1",
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

func TestPutEncrypted_RoundTripSeal(t *testing.T) {
	t.Parallel()
	var putBody []byte
	var putKey string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPut {
			putKey = r.URL.Path
			buf := make([]byte, r.ContentLength)
			_, _ = r.Body.Read(buf)
			putBody = buf
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	t.Cleanup(srv.Close)

	client, err := New(testCfg(srv.URL), testMasterB64(t), srv.Client())
	if err != nil {
		t.Fatal(err)
	}
	uri, err := client.PutEncrypted(context.Background(), ObjectKey("org/a.json"), []byte("secret-payload"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(uri.String(), "s3://ibex-sessions/") {
		t.Fatalf("uri=%s", uri)
	}
	if !strings.Contains(putKey, "org/a.json") {
		t.Fatalf("put key=%s", putKey)
	}
	if len(putBody) == 0 {
		t.Fatal("empty body")
	}
	mk, err := crypto.ParseMasterKeyBase64(testMasterB64(t))
	if err != nil {
		t.Fatal(err)
	}
	sealed, err := crypto.Seal(mk, "v1", []byte("x"))
	if err != nil {
		t.Fatal(err)
	}
	plain, err := crypto.Open(mk, sealed)
	if err != nil || string(plain) != "x" {
		t.Fatalf("open: %v %q", err, plain)
	}
}

func TestPutEncrypted_EmptyKey(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)
	client, err := New(testCfg(srv.URL), testMasterB64(t), srv.Client())
	if err != nil {
		t.Fatal(err)
	}
	_, err = client.PutEncrypted(context.Background(), ObjectKey(""), []byte("x"))
	if err == nil {
		t.Fatal("expected error")
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
	client, err := New(testCfg("http://127.0.0.1:9"), testMasterB64(t), nil)
	if err != nil {
		t.Fatal(err)
	}
	cases := []ObjectURI{"http://x", "s3://onlybucket", "s3://other/key"}
	for _, u := range cases {
		if err := client.DeleteURI(context.Background(), u); err == nil {
			t.Fatalf("expected error for %s", u)
		}
	}
}

func TestDeleteURI_NotFoundOK(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodDelete {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)
	client, err := New(testCfg(srv.URL), testMasterB64(t), srv.Client())
	if err != nil {
		t.Fatal(err)
	}
	if err := client.DeleteURI(context.Background(), ObjectURI("s3://ibex-sessions/missing")); err != nil {
		t.Fatal(err)
	}
}

func TestDeletePrefix_ListsAndDeletes(t *testing.T) {
	t.Parallel()
	deleted := map[string]bool{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && strings.Contains(r.URL.RawQuery, "list-type=2"):
			w.Header().Set("Content-Type", "application/xml")
			_, _ = w.Write([]byte(`<?xml version="1.0"?>
<ListBucketResult>
  <Contents><Key>org/a</Key></Contents>
  <Contents><Key>org/b</Key></Contents>
  <IsTruncated>false</IsTruncated>
</ListBucketResult>`))
		case r.Method == http.MethodDelete:
			deleted[r.URL.Path] = true
			w.WriteHeader(http.StatusNoContent)
		default:
			w.WriteHeader(http.StatusOK)
		}
	}))
	t.Cleanup(srv.Close)
	client, err := New(testCfg(srv.URL), testMasterB64(t), srv.Client())
	if err != nil {
		t.Fatal(err)
	}
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
	if err != nil || next != "tok" || len(keys) != 1 || keys[0] != "k1" {
		t.Fatalf("keys=%v next=%q err=%v", keys, next, err)
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
	cfg := ConfigFromEnv()
	if cfg.Endpoint != "http://localhost:9000" || cfg.Bucket != defaultBucket || cfg.Region != defaultRegion {
		t.Fatalf("%+v", cfg)
	}
}

func TestPutObject_HTTPError(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte("nope"))
	}))
	t.Cleanup(srv.Close)
	client, err := New(testCfg(srv.URL), testMasterB64(t), srv.Client())
	if err != nil {
		t.Fatal(err)
	}
	_, err = client.PutEncrypted(context.Background(), ObjectKey("x"), []byte("y"))
	if err == nil || !strings.Contains(err.Error(), "403") {
		t.Fatalf("err=%v", err)
	}
}

func TestListKeys_PaginationAndListError(t *testing.T) {
	t.Parallel()
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		if calls == 1 {
			w.Header().Set("Content-Type", "application/xml")
			_, _ = w.Write([]byte(`<?xml version="1.0"?>
<ListBucketResult>
  <Contents><Key>a</Key></Contents>
  <IsTruncated>true</IsTruncated>
  <NextContinuationToken>n1</NextContinuationToken>
</ListBucketResult>`))
			return
		}
		w.Header().Set("Content-Type", "application/xml")
		_, _ = w.Write([]byte(`<?xml version="1.0"?>
<ListBucketResult>
  <Contents><Key>b</Key></Contents>
  <IsTruncated>false</IsTruncated>
</ListBucketResult>`))
	}))
	t.Cleanup(srv.Close)
	client, err := New(testCfg(srv.URL), testMasterB64(t), srv.Client())
	if err != nil {
		t.Fatal(err)
	}
	keys, err := client.listKeys(context.Background(), ObjectKey("p/"))
	if err != nil || len(keys) != 2 {
		t.Fatalf("keys=%v err=%v", keys, err)
	}
}

func TestListPage_HTTPError(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("err"))
	}))
	t.Cleanup(srv.Close)
	client, err := New(testCfg(srv.URL), testMasterB64(t), srv.Client())
	if err != nil {
		t.Fatal(err)
	}
	_, _, err = client.listPage(context.Background(), ObjectKey("p/"), "")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestDeletePrefix_ListFailure(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
	}))
	t.Cleanup(srv.Close)
	client, err := New(testCfg(srv.URL), testMasterB64(t), srv.Client())
	if err != nil {
		t.Fatal(err)
	}
	if err := client.DeletePrefix(context.Background(), uuid.New()); err == nil {
		t.Fatal("expected error")
	}
}

func TestHTTPDo_TransportError(t *testing.T) {
	t.Parallel()
	client, err := New(testCfg("http://127.0.0.1:9"), testMasterB64(t), &http.Client{
		Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
			return nil, context.Canceled
		}),
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := client.deleteObject(context.Background(), ObjectKey("x")); err == nil {
		t.Fatal("expected transport error")
	}
	_, _, err = client.listPage(context.Background(), ObjectKey("p/"), "tok")
	if err == nil {
		t.Fatal("expected list transport error")
	}
}

func TestBuildCanonicalHeaders_SkipsAuthorization(t *testing.T) {
	t.Parallel()
	req, err := http.NewRequest(http.MethodGet, "http://example/x", nil)
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Authorization", "should-skip")
	req.Header.Set("X-Amz-Date", "20260101T000000Z")
	signed, canonical := buildCanonicalHeaders(req)
	if strings.Contains(signed, "authorization") || strings.Contains(canonical, "authorization") {
		t.Fatalf("signed=%q canonical=%q", signed, canonical)
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestPutEncrypted_EmptyKeyIDFailsSeal(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)
	client, err := New(testCfg(srv.URL), testMasterB64(t), srv.Client())
	if err != nil {
		t.Fatal(err)
	}
	client.cfg.KeyID = ""
	_, err = client.PutEncrypted(context.Background(), ObjectKey("x"), []byte("y"))
	if err == nil {
		t.Fatal("expected seal error")
	}
}

func TestDeletePrefix_DeleteFailure(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			w.Header().Set("Content-Type", "application/xml")
			_, _ = w.Write([]byte(`<?xml version="1.0"?><ListBucketResult>
  <Contents><Key>x</Key></Contents><IsTruncated>false</IsTruncated>
</ListBucketResult>`))
			return
		}
		w.WriteHeader(http.StatusInternalServerError)
	}))
	t.Cleanup(srv.Close)
	client, err := New(testCfg(srv.URL), testMasterB64(t), srv.Client())
	if err != nil {
		t.Fatal(err)
	}
	if err := client.DeletePrefix(context.Background(), uuid.New()); err == nil {
		t.Fatal("expected error")
	}
}

func TestListPage_BadXML(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("not-xml"))
	}))
	t.Cleanup(srv.Close)
	client, err := New(testCfg(srv.URL), testMasterB64(t), srv.Client())
	if err != nil {
		t.Fatal(err)
	}
	_, _, err = client.listPage(context.Background(), ObjectKey("p/"), "")
	if err == nil {
		t.Fatal("expected error")
	}
}
