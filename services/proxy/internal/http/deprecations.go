package http

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// DefaultDeprecationsFile is the committed deprecation record, relative to the
// repository root. It is the record of record for every surface; the proxy
// reads only its own "proxy" entries.
const DefaultDeprecationsFile = "engineering/architecture-v2/contracts/deprecations.json"

const (
	deprecationsSchema = "ibex.deprecations.v1"
	proxySurface       = "proxy"
	dateLayout         = "2006-01-02"

	headerDeprecation = "Deprecation"
	headerSunset      = "Sunset"
)

// statusAnnounced is the only status that has been told to consumers. A
// proposed entry is a plan and a withdrawn one was cancelled, so neither is
// announced on the wire.
const statusAnnounced = "announced"

// otherSurfaces are validated by services/api/scripts/check_deprecations.py.
// The proxy accepts their entries without inspecting them: it is not their
// emitter, and a second opinion here would disagree with the checker the first
// time the record gains a field for one of them.
var otherSurfaces = map[string]struct{}{"rest": {}, "grpc": {}, "mcp": {}}

// proxyStatuses is the ibex.deprecations.v1 status enum, applied to proxy
// entries because the emitter branches on it.
var proxyStatuses = map[string]struct{}{
	"proposed":  {},
	"announced": {},
	"withdrawn": {},
}

// deprecationRecord is the subset of ibex.deprecations.v1 the proxy reads. It
// is decoded leniently: unknown fields belong to the record's other surfaces
// and are the checker's business, not this loader's.
type deprecationRecord struct {
	Schema  string             `json:"schema"`
	Entries []deprecationEntry `json:"entries"`
}

type deprecationEntry struct {
	ID                 string `json:"id"`
	Surface            string `json:"surface"`
	Path               string `json:"path"`
	Status             string `json:"status"`
	NoticeDate         string `json:"notice_date"`
	AnnouncedOn        string `json:"announced_on"`
	SunsetDate         string `json:"sunset_date"`
	HeadersImplemented bool   `json:"headers_implemented"`
}

// deprecationNotice is the immutable per-path payload. Both header values are
// formatted once at startup so a request does no date arithmetic and no
// formatting.
type deprecationNotice struct {
	// deprecation is an RFC 9745 Date naming the notice time, e.g. "@1798761600".
	deprecation string
	// sunset is an RFC 8594 HTTP-date naming the removal date.
	sunset string
	// sunsetAt is the removal date at 00:00 UTC, used to stop announcing after it.
	sunsetAt time.Time
}

// expired reports whether the sunset date is behind now's UTC date. The entry
// announces through its sunset day and stops on the first day after it.
func (n deprecationNotice) expired(now time.Time) bool {
	year, month, day := now.UTC().Date()
	return time.Date(year, month, day, 0, 0, 0, 0, time.UTC).After(n.sunsetAt)
}

// deprecationNotices maps one exact request path to its notice. Exact matching
// is deliberate: the proxy serves a fixed route set, so a path identifies a
// contract unambiguously, and a route added later under a shared prefix can
// never inherit a deprecation that was not recorded for it.
type deprecationNotices map[string]deprecationNotice

// loadProxyDeprecationNotices reads the record and returns the notices the
// proxy may announce, keyed by exact request path.
//
// configured is IBEX_PROXY_DEPRECATIONS_FILE. Empty selects
// DefaultDeprecationsFile, resolved against the working directory and then its
// ancestors so a checkout works from any package directory.
//
// A record that is absent means no deprecated route: a deployment that ships
// no record announces nothing, and the committed record is empty today. Every
// other failure — an unreadable file, invalid JSON, a foreign schema, or an
// entry this emitter cannot honour faithfully — is returned so startup fails.
// Announcing nothing because a record was silently misread is the failure this
// loader exists to prevent.
func loadProxyDeprecationNotices(configured string) (deprecationNotices, error) {
	path, ok := resolveDeprecationsFile(configured)
	if !ok {
		return nil, nil
	}
	data, err := os.ReadFile(filepath.Clean(path)) //nolint:gosec // operator config or repo path, never request input
	if errors.Is(err, fs.ErrNotExist) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	record, err := decodeDeprecationRecord(data)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return buildDeprecationNotices(record)
}

// resolveDeprecationsFile returns the record path to read. The second result is
// false when no default record exists anywhere above the working directory.
func resolveDeprecationsFile(configured string) (string, bool) {
	if path := strings.TrimSpace(configured); path != "" {
		return path, true
	}
	dir, err := os.Getwd()
	if err != nil {
		return "", false
	}
	for {
		candidate := filepath.Join(dir, DefaultDeprecationsFile)
		if info, statErr := os.Stat(candidate); statErr == nil && !info.IsDir() {
			return candidate, true
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", false
		}
		dir = parent
	}
}

func decodeDeprecationRecord(data []byte) (deprecationRecord, error) {
	var record deprecationRecord
	dec := json.NewDecoder(bytes.NewReader(data))
	if err := dec.Decode(&record); err != nil {
		return deprecationRecord{}, fmt.Errorf("malformed record: %w", err)
	}
	var trailing any
	if err := dec.Decode(&trailing); !errors.Is(err, io.EOF) {
		return deprecationRecord{}, errors.New("malformed record: trailing data after the top-level object")
	}
	if record.Schema != deprecationsSchema {
		return deprecationRecord{}, fmt.Errorf("schema %q is not %q", record.Schema, deprecationsSchema)
	}
	return record, nil
}

// buildDeprecationNotices keeps the proxy entries that announce a deprecation
// and drops the rest: an entry with headers_implemented false has no emitter,
// and a proposed or withdrawn entry has not been announced.
func buildDeprecationNotices(record deprecationRecord) (deprecationNotices, error) {
	notices := make(deprecationNotices, len(record.Entries))
	for _, entry := range record.Entries {
		if err := checkEntrySurface(entry); err != nil {
			return nil, err
		}
		if entry.Surface != proxySurface {
			continue
		}
		notice, err := proxyNoticeFor(entry)
		if err != nil {
			return nil, err
		}
		if notice == nil {
			continue
		}
		if _, duplicate := notices[entry.Path]; duplicate {
			return nil, fmt.Errorf("entry %q: path %q is already announced by another proxy entry", entry.ID, entry.Path)
		}
		notices[entry.Path] = *notice
	}
	if len(notices) == 0 {
		return nil, nil
	}
	return notices, nil
}

func checkEntrySurface(entry deprecationEntry) error {
	if entry.Surface == proxySurface {
		return nil
	}
	if _, known := otherSurfaces[entry.Surface]; known {
		return nil
	}
	return fmt.Errorf("entry %q: unknown surface %q", entry.ID, entry.Surface)
}

// proxyNoticeFor validates one proxy entry and returns its notice, or nil when
// the entry must not be announced.
//
// Selector and status are checked on every proxy entry because they decide
// whether the entry is addressable and whether it emits at all. The dates are
// checked only for an entry that announces: the checker owns the shape of an
// entry that does not, and a second validator here would drift from it.
func proxyNoticeFor(entry deprecationEntry) (*deprecationNotice, error) {
	if err := validateProxyPath(entry); err != nil {
		return nil, err
	}
	if _, ok := proxyStatuses[entry.Status]; !ok {
		return nil, fmt.Errorf(
			"entry %q: status %q is not proposed, announced, or withdrawn", entry.ID, entry.Status)
	}
	if entry.Status != statusAnnounced || !entry.HeadersImplemented {
		return nil, nil
	}
	noticeAt, err := noticeTime(entry)
	if err != nil {
		return nil, err
	}
	sunsetAt, err := parseEntryDate(entry.ID, "sunset_date", entry.SunsetDate)
	if err != nil {
		return nil, err
	}
	return &deprecationNotice{
		deprecation: "@" + strconv.FormatInt(noticeAt.Unix(), 10),
		sunset:      sunsetAt.Format(http.TimeFormat),
		sunsetAt:    sunsetAt,
	}, nil
}

// noticeTime is the time the Deprecation header names. It is the date consumers
// were told — announced_on — because that is when the support window starts; a
// record without one falls back to the planned notice_date.
func noticeTime(entry deprecationEntry) (time.Time, error) {
	if announced := strings.TrimSpace(entry.AnnouncedOn); announced != "" {
		return parseEntryDate(entry.ID, "announced_on", announced)
	}
	return parseEntryDate(entry.ID, "notice_date", entry.NoticeDate)
}

// validateProxyPath requires one exact route path. A trailing slash, a path
// template, or a character no served route contains would never match a
// request, and a notice that silently never fires is exactly what this loader
// must not allow, so each is a startup error rather than an ignored entry.
func validateProxyPath(entry deprecationEntry) error {
	path := entry.Path
	if !strings.HasPrefix(path, "/") {
		return fmt.Errorf("entry %q: proxy path %q must start with /", entry.ID, path)
	}
	if strings.HasSuffix(path, "/") || strings.ContainsAny(path, "{}?# \t") {
		return fmt.Errorf(
			"entry %q: proxy path %q must be one exact route path (no trailing slash, no template, no query)",
			entry.ID, path)
	}
	return nil
}

func parseEntryDate(id, field, value string) (time.Time, error) {
	parsed, err := time.Parse(dateLayout, value)
	if err != nil {
		return time.Time{}, fmt.Errorf("entry %q: %s %q is not YYYY-MM-DD", id, field, value)
	}
	return parsed, nil
}

// deprecationHeadersMiddleware announces a recorded deprecation on the response
// of the exact path it names, and sets nothing on any other response.
//
// It sets the headers before calling the wrapped handler and never wraps the
// ResponseWriter, so http.Flusher and http.NewResponseController keep seeing
// the real writer and SSE streaming keeps its flush and write-deadline
// behaviour. An empty record returns next unchanged: no header, no wrapper, no
// per-request work.
func deprecationHeadersMiddleware(notices deprecationNotices) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		if len(notices) == 0 {
			return next
		}
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if notice, ok := notices[r.URL.Path]; ok && !notice.expired(time.Now()) {
				header := w.Header()
				header.Set(headerDeprecation, notice.deprecation)
				header.Set(headerSunset, notice.sunset)
			}
			next.ServeHTTP(w, r)
		})
	}
}
