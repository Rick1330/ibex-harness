package objectstore

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/xml"
	"fmt"
	"net/http"
	"sort"
	"strings"
	"time"
)

// awsV4Signer signs path-style S3 requests (MinIO-compatible).
type awsV4Signer struct {
	creds  Credentials
	region string
}

func newAWSV4Signer(creds Credentials, region string) *awsV4Signer {
	return &awsV4Signer{creds: creds, region: region}
}

func (s *awsV4Signer) sign(req *http.Request) {
	now := time.Now().UTC()
	amzDate := now.Format("20060102T150405Z")
	dateStamp := now.Format("20060102")
	req.Header.Set("Host", req.URL.Host)
	req.Header.Set("X-Amz-Date", amzDate)
	req.Header.Set("X-Amz-Content-Sha256", "UNSIGNED-PAYLOAD")

	signedHeaders, canonicalHdrs := buildCanonicalHeaders(req)
	canonicalRequest := strings.Join([]string{
		req.Method,
		req.URL.EscapedPath(),
		req.URL.RawQuery,
		canonicalHdrs,
		signedHeaders,
		"UNSIGNED-PAYLOAD",
	}, "\n")
	crHash := sha256.Sum256([]byte(canonicalRequest))
	scope := dateStamp + "/" + s.region + "/s3/aws4_request"
	stringToSign := strings.Join([]string{
		"AWS4-HMAC-SHA256",
		amzDate,
		scope,
		hex.EncodeToString(crHash[:]),
	}, "\n")
	sig := hex.EncodeToString(hmacSHA256(deriveSigningKey(s.creds.SecretKey, dateStamp, s.region), []byte(stringToSign)))
	req.Header.Set("Authorization", fmt.Sprintf(
		"AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s",
		s.creds.AccessKey, scope, signedHeaders, sig,
	))
}

func buildCanonicalHeaders(req *http.Request) (signed string, canonical string) {
	lower := make(map[string]string, len(req.Header))
	keys := make([]string, 0, len(req.Header))
	for orig, vals := range req.Header {
		lk := strings.ToLower(orig)
		if lk == "authorization" {
			continue
		}
		lower[lk] = strings.TrimSpace(strings.Join(vals, ","))
		keys = append(keys, lk)
	}
	sort.Strings(keys)
	var b strings.Builder
	for _, k := range keys {
		b.WriteString(k)
		b.WriteByte(':')
		b.WriteString(lower[k])
		b.WriteByte('\n')
	}
	return strings.Join(keys, ";"), b.String()
}

func deriveSigningKey(secret, date, region string) []byte {
	kDate := hmacSHA256([]byte("AWS4"+secret), []byte(date))
	kRegion := hmacSHA256(kDate, []byte(region))
	kService := hmacSHA256(kRegion, []byte("s3"))
	return hmacSHA256(kService, []byte("aws4_request"))
}

func hmacSHA256(key, data []byte) []byte {
	m := hmac.New(sha256.New, key)
	_, _ = m.Write(data)
	return m.Sum(nil)
}

type listObjectsV2Result struct {
	Contents []struct {
		Key string `xml:"Key"`
	} `xml:"Contents"`
	IsTruncated           bool   `xml:"IsTruncated"`
	NextContinuationToken string `xml:"NextContinuationToken"`
	NextMarker            string `xml:"NextMarker"`
}

func parseListObjectsV2(body []byte) ([]ObjectKey, string, error) {
	var parsed listObjectsV2Result
	if err := xml.Unmarshal(body, &parsed); err != nil {
		return nil, "", fmt.Errorf("objectstore: list xml: %w", err)
	}
	keys := make([]ObjectKey, 0, len(parsed.Contents))
	for _, ctn := range parsed.Contents {
		keys = append(keys, ObjectKey(ctn.Key))
	}
	if !parsed.IsTruncated {
		return keys, "", nil
	}
	next := parsed.NextContinuationToken
	if next == "" {
		next = parsed.NextMarker
	}
	return keys, next, nil
}
