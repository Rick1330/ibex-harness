package session

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
)

// ErrProviderResponseTooLarge is returned when a provider body exceeds MaxProviderResponseBytes.
var ErrProviderResponseTooLarge = errors.New("provider response exceeds size limit")

// WriteJSONBody writes opaque OpenAI-compatible JSON to the response writer.
// The io.Copy error is intentionally discarded once headers/body streaming to
// the client has begun; the peer already received a partial response.
func WriteJSONBody(w http.ResponseWriter, body []byte) {
	// Opaque OpenAI-compatible JSON passthrough (Content-Type: application/json).
	// Not an HTML response; Codacy/Opengrep XSS on ResponseWriter is a false positive.
	_, _ = io.Copy(w, bytes.NewReader(body)) // nosemgrep: go.lang.security.audit.xss.no-direct-write-to-responsewriter.no-direct-write-to-responsewriter
}

// ReadAllBody reads a provider response body capped at MaxProviderResponseBytes.
func ReadAllBody(r io.Reader) ([]byte, error) {
	return readLimitedBody(r, validation.MaxProviderResponseBytes)
}

func readLimitedBody(r io.Reader, limit int64) ([]byte, error) {
	limited := io.LimitReader(r, limit+1)
	body, err := io.ReadAll(limited)
	if err != nil {
		return nil, fmt.Errorf("read provider body: %w", err)
	}
	if int64(len(body)) > limit {
		return nil, ErrProviderResponseTooLarge
	}
	return body, nil
}

// CompletionTextFromJSON extracts choices[0].message.content from a chat JSON body.
func CompletionTextFromJSON(body []byte) string {
	var wire struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.Unmarshal(body, &wire); err != nil || len(wire.Choices) == 0 {
		return ""
	}
	return wire.Choices[0].Message.Content
}

// SetResponseHeader echoes X-IBEX-Session-ID when a sticky external id is present.
func SetResponseHeader(w http.ResponseWriter, rs Resolved) {
	if rs.ExternalID == "" {
		return
	}
	w.Header().Set(HeaderSessionID, rs.ExternalID)
}
