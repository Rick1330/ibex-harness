package sessionjwt_test

import (
	"encoding/base64"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
)

func b64urlJSON(v any) string {
	raw, err := json.Marshal(v)
	if err != nil {
		panic(err)
	}
	return base64.RawURLEncoding.EncodeToString(raw)
}

func testVerifier(t *testing.T) *sessionjwt.Verifier {
	t.Helper()
	priv, _ := mustRSAPrivatePEM(t)
	return mustVerifier(t, mustPublicPEM(t, priv), "ibex-auth", "ibex-dashboard")
}

func TestVerify_RejectsShortToken(t *testing.T) {
	if _, err := testVerifier(t).Verify(sessionjwt.RawToken("a.b"), sessionjwt.KindAccess); err == nil {
		t.Fatal("expected split error")
	}
}

func TestVerify_RejectsInvalidHeaderEncoding(t *testing.T) {
	if _, err := testVerifier(t).Verify(sessionjwt.RawToken("!!!.payload.sig"), sessionjwt.KindAccess); err == nil {
		t.Fatal("expected bad header")
	}
}

func TestVerify_RejectsNonRS256Header(t *testing.T) {
	hsHeader := b64urlJSON(map[string]string{"alg": "HS256", "typ": "JWT", "kid": "v1"})
	if _, err := testVerifier(t).Verify(sessionjwt.RawToken(hsHeader+".payload.sig"), sessionjwt.KindAccess); err == nil {
		t.Fatal("expected alg mismatch")
	}
}

func TestVerify_RejectsMissingKidHeader(t *testing.T) {
	noKid := b64urlJSON(map[string]string{"alg": "RS256", "typ": "JWT"})
	if _, err := testVerifier(t).Verify(sessionjwt.RawToken(noKid+".payload.sig"), sessionjwt.KindAccess); err == nil {
		t.Fatal("expected missing kid")
	}
}

func issuedAccessParts(t *testing.T) (*sessionjwt.Verifier, []string) {
	t.Helper()
	priv, privPEM := mustRSAPrivatePEM(t)
	pub := mustPublicPEM(t, priv)
	iss, err := sessionjwt.NewIssuer(testIssuerConfig(privPEM, time.Minute, time.Hour, time.Minute))
	requireNoErr(t, err)
	ver := mustVerifier(t, pub, "ibex-auth", "ibex-dashboard")
	access, _, _, _, err := iss.IssuePair(sessionjwt.IssuePairParams{Subject: "u", OrgID: "o", Permissions: 1})
	requireNoErr(t, err)
	return ver, strings.Split(access, ".")
}

func TestVerify_RejectsBadSignatureEncoding(t *testing.T) {
	ver, parts := issuedAccessParts(t)
	if _, err := ver.Verify(sessionjwt.RawToken(parts[0]+"."+parts[1]+".!!!"), sessionjwt.KindAccess); err == nil {
		t.Fatal("expected bad signature encoding")
	}
}

func TestVerify_RejectsBadPayloadEncoding(t *testing.T) {
	ver, parts := issuedAccessParts(t)
	if _, err := ver.Verify(sessionjwt.RawToken(parts[0]+".!!!."+parts[2]), sessionjwt.KindAccess); err == nil {
		t.Fatal("expected bad payload")
	}
}

func TestVerify_RejectsNonJSONPayload(t *testing.T) {
	ver, parts := issuedAccessParts(t)
	payload := base64.RawURLEncoding.EncodeToString([]byte("not-json"))
	if _, err := ver.Verify(sessionjwt.RawToken(parts[0]+"."+payload+"."+parts[2]), sessionjwt.KindAccess); err == nil {
		t.Fatal("expected malformed payload json")
	}
}
