package objectstore

import (
	"context"
	"encoding/xml"
	"fmt"
	"net/http"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	v4 "github.com/aws/aws-sdk-go-v2/aws/signer/v4"
)

// awsV4Signer signs path-style S3 requests with the official AWS SDK v2 SigV4
// implementation. Hand-rolled HMAC signing is forbidden (AGENTS.md §5.4: no custom crypto).
type awsV4Signer struct {
	creds  aws.Credentials
	region string
	inner  *v4.Signer
}

func newAWSV4Signer(creds Credentials, region string) *awsV4Signer {
	return &awsV4Signer{
		creds: aws.Credentials{
			AccessKeyID:     creds.AccessKey,
			SecretAccessKey: creds.SecretKey,
		},
		region: region,
		// S3 expects a single-escaped path; we escape segments in objectURL.
		inner: v4.NewSigner(func(o *v4.SignerOptions) {
			o.DisableURIPathEscaping = true
		}),
	}
}

func (s *awsV4Signer) sign(ctx context.Context, req *http.Request) error {
	return s.inner.SignHTTP(ctx, s.creds, req, "UNSIGNED-PAYLOAD", "s3", s.region, time.Now().UTC())
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
