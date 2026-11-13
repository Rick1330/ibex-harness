package http

import (
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

const (
	testDeprecationNotice = "2027-01-01"
	testDeprecationSunset = "2027-06-30"
)

func writeDeprecationRecord(t *testing.T, entries string) string {
	t.Helper()
	body := `{"schema":"ibex.deprecations.v1","entries":[` + entries + `]}`
	path := filepath.Join(t.TempDir(), "deprecations.json")
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatalf("write record: %v", err)
	}
	return path
}

// announcedProxyEntry is a valid proxy entry that announces its deprecation.
func announcedProxyEntry(id, path string) string {
	return `{"id":"` + id + `","surface":"proxy","path":"` + path + `",` +
		`"stability":"stable","notice_date":"` + testDeprecationNotice + `",` +
		`"sunset_date":"` + testDeprecationSunset + `","status":"announced",` +
		`"successor":"/v2/chat/completions","headers_implemented":true,` +
		`"evidence":"engineering/architecture-v2/16-compatibility-and-versioning.md"}`
}

func TestUnit_loadProxyDeprecationNotices_missingFileIsNoNotices(t *testing.T) {
	t.Parallel()
	notices, err := loadProxyDeprecationNotices(filepath.Join(t.TempDir(), "absent.json"))
	if err != nil {
		t.Fatalf("missing record must not fail startup: %v", err)
	}
	if notices != nil {
		t.Fatalf("notices: %v", notices)
	}
}

func TestUnit_loadProxyDeprecationNotices_emptyRecordIsNoNotices(t *testing.T) {
	t.Parallel()
	notices, err := loadProxyDeprecationNotices(writeDeprecationRecord(t, ""))
	if err != nil {
		t.Fatalf("empty record must not fail startup: %v", err)
	}
	if notices != nil {
		t.Fatalf("notices: %v", notices)
	}
}

func TestUnit_loadProxyDeprecationNotices_malformedRecordFailsStartup(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		body string
	}{
		{name: "empty file", body: ""},
		{name: "truncated json", body: `{"schema":`},
		{name: "wrong schema", body: `{"schema":"ibex.deprecations.v0","entries":[]}`},
		{name: "missing schema", body: `{"entries":[]}`},
		{name: "trailing data", body: `{"schema":"ibex.deprecations.v1","entries":[]}{}`},
		{
			name: "unknown surface",
			body: `{"schema":"ibex.deprecations.v1","entries":[{"id":"d1","surface":"prox",` +
				`"path":"/v1/chat/completions"}]}`,
		},
		{
			name: "proxy entry without path",
			body: `{"schema":"ibex.deprecations.v1","entries":[{"id":"d1","surface":"proxy",` +
				`"status":"announced","notice_date":"2027-01-01","sunset_date":"2027-06-30",` +
				`"headers_implemented":true}]}`,
		},
		{
			name: "path without leading slash",
			body: `{"schema":"ibex.deprecations.v1","entries":[{"id":"d1","surface":"proxy",` +
				`"path":"v1/chat/completions","status":"announced","notice_date":"2027-01-01",` +
				`"sunset_date":"2027-06-30","headers_implemented":true}]}`,
		},
		{
			name: "path with trailing slash",
			body: `{"schema":"ibex.deprecations.v1","entries":[{"id":"d1","surface":"proxy",` +
				`"path":"/v1/chat/completions/","status":"announced","notice_date":"2027-01-01",` +
				`"sunset_date":"2027-06-30","headers_implemented":true}]}`,
		},
		{
			name: "path template",
			body: `{"schema":"ibex.deprecations.v1","entries":[{"id":"d1","surface":"proxy",` +
				`"path":"/v1/orgs/{org_id}/sessions","status":"announced","notice_date":"2027-01-01",` +
				`"sunset_date":"2027-06-30","headers_implemented":true}]}`,
		},
		{
			name: "unknown status",
			body: `{"schema":"ibex.deprecations.v1","entries":[{"id":"d1","surface":"proxy",` +
				`"path":"/v1/chat/completions","status":"deprecated","notice_date":"2027-01-01",` +
				`"sunset_date":"2027-06-30","headers_implemented":true}]}`,
		},
		{
			name: "notice_date is not YYYY-MM-DD",
			body: `{"schema":"ibex.deprecations.v1","entries":[{"id":"d1","surface":"proxy",` +
				`"path":"/v1/chat/completions","status":"announced","notice_date":"2027-1-1",` +
				`"sunset_date":"2027-06-30","headers_implemented":true}]}`,
		},
		{
			name: "sunset_date is not YYYY-MM-DD",
			body: `{"schema":"ibex.deprecations.v1","entries":[{"id":"d1","surface":"proxy",` +
				`"path":"/v1/chat/completions","status":"announced","notice_date":"2027-01-01",` +
				`"sunset_date":"June 30 2027","headers_implemented":true}]}`,
		},
		{
			name: "two announced entries claim one path",
			body: `{"schema":"ibex.deprecations.v1","entries":[` +
				announcedProxyEntry("d1", "/v1/chat/completions") + `,` +
				announcedProxyEntry("d2", "/v1/chat/completions") + `]}`,
		},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			path := filepath.Join(t.TempDir(), "deprecations.json")
			if err := os.WriteFile(path, []byte(tc.body), 0o600); err != nil {
				t.Fatalf("write record: %v", err)
			}
			notices, err := loadProxyDeprecationNotices(path)
			if err == nil {
				t.Fatalf("expected startup error, got notices=%v", notices)
			}
			if notices != nil {
				t.Fatalf("notices on failure: %v", notices)
			}
		})
	}
}

func TestUnit_loadProxyDeprecationNotices_announcedProxyEntry(t *testing.T) {
	t.Parallel()
	path := writeDeprecationRecord(t, announcedProxyEntry("d1", "/v1/chat/completions"))
	notices, err := loadProxyDeprecationNotices(path)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	notice, ok := notices["/v1/chat/completions"]
	if !ok {
		t.Fatalf("no notice for the recorded path: %v", notices)
	}
	noticeAt, err := time.Parse(dateLayout, testDeprecationNotice)
	if err != nil {
		t.Fatalf("parse notice date: %v", err)
	}
	wantDeprecation := "@" + strconv.FormatInt(noticeAt.Unix(), 10)
	if notice.deprecation != wantDeprecation {
		t.Fatalf("Deprecation: got %q want %q", notice.deprecation, wantDeprecation)
	}
	sunsetAt, err := time.Parse(dateLayout, testDeprecationSunset)
	if err != nil {
		t.Fatalf("parse sunset date: %v", err)
	}
	if want := sunsetAt.Format(http.TimeFormat); notice.sunset != want {
		t.Fatalf("Sunset: got %q want %q", notice.sunset, want)
	}
	if !notice.sunsetAt.Equal(sunsetAt) {
		t.Fatalf("sunsetAt: got %s want %s", notice.sunsetAt, sunsetAt)
	}
}

func TestUnit_loadProxyDeprecationNotices_dropsEntriesThatDoNotAnnounce(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		entry string
	}{
		{
			name: "headers not implemented",
			entry: `{"id":"d1","surface":"proxy","path":"/v1/chat/completions","stability":"stable",` +
				`"notice_date":"2027-01-01","sunset_date":"2027-06-30","status":"announced",` +
				`"successor":"/v2/chat/completions","headers_implemented":false,"evidence":"x.md"}`,
		},
		{
			name: "proposed",
			entry: `{"id":"d1","surface":"proxy","path":"/v1/chat/completions","stability":"stable",` +
				`"notice_date":"2027-01-01","sunset_date":"2027-06-30","status":"proposed",` +
				`"successor":"/v2/chat/completions","headers_implemented":true,"evidence":"x.md"}`,
		},
		{
			name: "withdrawn",
			entry: `{"id":"d1","surface":"proxy","path":"/v1/chat/completions","stability":"stable",` +
				`"notice_date":"2027-01-01","sunset_date":"2027-06-30","status":"withdrawn",` +
				`"successor":"/v2/chat/completions","headers_implemented":true,"evidence":"x.md"}`,
		},
		{
			// A proposed entry is not announced, so the proxy reads only its
			// selector and status; the checker owns the rest of its shape.
			name: "proposed entry with undated plan",
			entry: `{"id":"d1","surface":"proxy","path":"/v1/chat/completions","stability":"stable",` +
				`"notice_date":"","sunset_date":"","status":"proposed",` +
				`"successor":"/v2/chat/completions","headers_implemented":false,"evidence":"x.md"}`,
		},
		{
			// The proxy is not the REST emitter and does not second-guess the
			// checker that validates rest entries.
			name:  "rest entry",
			entry: `{"id":"d1","surface":"rest","contract_id":"chat.completions"}`,
		},
		{
			name:  "grpc entry",
			entry: `{"id":"d1","surface":"grpc","contract_id":"ibex.auth.v1.AuthService/Validate"}`,
		},
		{
			name:  "mcp entry",
			entry: `{"id":"d1","surface":"mcp","tool":"memory.search","server":"memory"}`,
		},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			notices, err := loadProxyDeprecationNotices(writeDeprecationRecord(t, tc.entry))
			if err != nil {
				t.Fatalf("load: %v", err)
			}
			if notices != nil {
				t.Fatalf("expected no notices, got %v", notices)
			}
		})
	}
}

// TestUnit_loadProxyDeprecationNotices_deprecationNamesTheAnnouncementDate pins
// the header date to announced_on: the support window runs from the date
// consumers were told, not from the planned notice_date.
func TestUnit_loadProxyDeprecationNotices_deprecationNamesTheAnnouncementDate(t *testing.T) {
	t.Parallel()
	entry := `{"id":"d1","surface":"proxy","path":"/v1/chat/completions","stability":"stable",` +
		`"notice_date":"2026-12-01","announced_on":"2027-01-01","sunset_date":"2027-06-30",` +
		`"status":"announced","successor":"/v2/chat/completions","headers_implemented":true,"evidence":"x.md"}`
	notices, err := loadProxyDeprecationNotices(writeDeprecationRecord(t, entry))
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	announcedAt, err := time.Parse(dateLayout, "2027-01-01")
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if want := "@" + strconv.FormatInt(announcedAt.Unix(), 10); notices["/v1/chat/completions"].deprecation != want {
		t.Fatalf("Deprecation: got %q want %q", notices["/v1/chat/completions"].deprecation, want)
	}
}

func TestUnit_loadProxyDeprecationNotices_rejectsBadAnnouncedOn(t *testing.T) {
	t.Parallel()
	entry := `{"id":"d1","surface":"proxy","path":"/v1/chat/completions","stability":"stable",` +
		`"notice_date":"2026-12-01","announced_on":"Jan 1 2027","sunset_date":"2027-06-30",` +
		`"status":"announced","successor":"/v2/chat/completions","headers_implemented":true,"evidence":"x.md"}`
	if _, err := loadProxyDeprecationNotices(writeDeprecationRecord(t, entry)); err == nil {
		t.Fatal("expected a startup error for a malformed announced_on")
	}
}

func TestUnit_resolveDeprecationsFile(t *testing.T) {
	t.Parallel()
	t.Run("configured path wins", func(t *testing.T) {
		t.Parallel()
		got, ok := resolveDeprecationsFile(" /tmp/record.json ")
		if !ok || got != "/tmp/record.json" {
			t.Fatalf("got (%q, %v)", got, ok)
		}
	})
	t.Run("default resolves to the committed record", func(t *testing.T) {
		t.Parallel()
		got, ok := resolveDeprecationsFile("")
		if !ok {
			t.Fatal("default record not found; run the test from inside the repository")
		}
		if !strings.HasSuffix(got, DefaultDeprecationsFile) {
			t.Fatalf("resolved %q, want a path ending in %q", got, DefaultDeprecationsFile)
		}
		if info, err := os.Stat(got); err != nil || info.IsDir() {
			t.Fatalf("resolved %q is not a file: %v", got, err)
		}
	})
}
