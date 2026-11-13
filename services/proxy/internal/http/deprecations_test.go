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

// badRecord is one record body the loader must refuse, with the behaviour it
// pins.
type badRecord struct {
	name string
	body string
}

// assertNoNotices loads the record at path and requires it to announce nothing.
func assertNoNotices(t *testing.T, path string) {
	t.Helper()
	notices, err := loadProxyDeprecationNotices(path)
	if err != nil {
		t.Fatalf("record %s must not fail startup: %v", path, err)
	}
	if notices != nil {
		t.Fatalf("expected no notices from %s, got %v", path, notices)
	}
}

// TestUnit_loadProxyDeprecationNotices_absentOrEmptyRecordIsNoNotices pins that
// a deployment shipping no record, and a record with no entries, both announce
// nothing and both start up.
func TestUnit_loadProxyDeprecationNotices_absentOrEmptyRecordIsNoNotices(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		path func(t *testing.T) string
	}{
		{
			name: "missing file",
			path: func(t *testing.T) string {
				t.Helper()
				return filepath.Join(t.TempDir(), "absent.json")
			},
		},
		{
			name: "empty record",
			path: func(t *testing.T) string {
				t.Helper()
				return writeDeprecationRecord(t, "")
			},
		},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			assertNoNotices(t, tc.path(t))
		})
	}
}

// recordShapeCases are records the decoder itself must refuse: none of them can
// be honoured faithfully, so startup fails before any notice is built.
func recordShapeCases() []badRecord {
	return []badRecord{
		{name: "empty file", body: ""},
		{name: "truncated json", body: `{"schema":`},
		{name: "wrong schema", body: `{"schema":"ibex.deprecations.v0","entries":[]}`},
		{name: "missing schema", body: `{"entries":[]}`},
		{name: "trailing data", body: `{"schema":"ibex.deprecations.v1","entries":[]}{}`},
	}
}

// entryValidationCases are records whose entries the loader must refuse: an
// entry it cannot honour faithfully is a startup error, never a silent drop.
func entryValidationCases() []badRecord {
	return []badRecord{
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
}

// assertRecordsRejected requires every case to fail startup without returning
// notices.
func assertRecordsRejected(t *testing.T, cases []badRecord) {
	t.Helper()
	for _, tc := range cases {
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

// TestUnit_loadProxyDeprecationNotices_malformedRecordFailsStartup splits the
// refusal cases by the layer that must refuse them.
func TestUnit_loadProxyDeprecationNotices_malformedRecordFailsStartup(t *testing.T) {
	t.Parallel()
	t.Run("record shape", func(t *testing.T) {
		t.Parallel()
		assertRecordsRejected(t, recordShapeCases())
	})
	t.Run("entry validation", func(t *testing.T) {
		t.Parallel()
		assertRecordsRejected(t, entryValidationCases())
	})
}

// duplicateTestPath is the one path every duplicate-scope case names, so the
// assertions can look it up without repeating the literal.
const duplicateTestPath = "/v1/chat/completions"

// nonAnnouncingProxyEntry is a valid proxy entry that does not announce, so the
// loader drops it and it never enters the notice map. headers_implemented is
// false because the record checker rejects true on a proposed or withdrawn
// entry, and the scope below mirrors the checker's.
func nonAnnouncingProxyEntry(id, status string) string {
	return `{"id":"` + id + `","surface":"proxy","path":"` + duplicateTestPath + `",` +
		`"stability":"stable","notice_date":"` + testDeprecationNotice + `",` +
		`"sunset_date":"` + testDeprecationSunset + `","status":"` + status + `",` +
		`"successor":"/v2/chat/completions","headers_implemented":false,` +
		`"evidence":"engineering/architecture-v2/16-compatibility-and-versioning.md"}`
}

// duplicatePathCase is one record whose entries share a path, with the outcome
// the loader must produce for it.
type duplicatePathCase struct {
	name    string
	entries []string
	// wantErr is the exact startup error; empty means the record must load.
	wantErr string
	// wantNotice is whether the shared path is still announced after a load.
	wantNotice bool
}

// duplicatePathCases are the records with a repeated path. The scope is the
// loader's notice map, not the surface: only an entry it announces is a
// duplicate, so a proposal may name the same path as an announcement, and two
// proposals may name the same path as each other.
// services/api/scripts/check_deprecations.py mirrors exactly this scope for
// proxy entries.
func duplicatePathCases() []duplicatePathCase {
	return []duplicatePathCase{
		{
			name: "two announcing entries fail startup",
			entries: []string{
				announcedProxyEntry("d1", duplicateTestPath),
				announcedProxyEntry("d2", duplicateTestPath),
			},
			wantErr: `entry "d2": path "/v1/chat/completions" is already announced by another proxy entry`,
		},
		{
			name: "announcement then proposal is allowed",
			entries: []string{
				announcedProxyEntry("d1", duplicateTestPath),
				nonAnnouncingProxyEntry("d2", "proposed"),
			},
			wantNotice: true,
		},
		{
			name: "proposal then announcement is allowed",
			entries: []string{
				nonAnnouncingProxyEntry("d1", "proposed"),
				announcedProxyEntry("d2", duplicateTestPath),
			},
			wantNotice: true,
		},
		{
			name: "two proposals are allowed",
			entries: []string{
				nonAnnouncingProxyEntry("d1", "proposed"),
				nonAnnouncingProxyEntry("d2", "proposed"),
			},
		},
		{
			name: "two withdrawn entries are allowed",
			entries: []string{
				nonAnnouncingProxyEntry("d1", "withdrawn"),
				nonAnnouncingProxyEntry("d2", "withdrawn"),
			},
		},
	}
}

// TestUnit_loadProxyDeprecationNotices_duplicatePathScope pins which repeated
// paths are refused and which are not. The refusal itself is already covered as
// a rejection case; this pins the message that names the colliding entry and
// path, and the boundary: only a second announcing entry on a path is an error.
func TestUnit_loadProxyDeprecationNotices_duplicatePathScope(t *testing.T) {
	t.Parallel()
	for _, tc := range duplicatePathCases() {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			notices, err := loadProxyDeprecationNotices(writeDeprecationRecord(t, strings.Join(tc.entries, ",")))
			if tc.wantErr != "" {
				if err == nil {
					t.Fatalf("expected startup error %q, got notices=%v", tc.wantErr, notices)
				}
				if got := err.Error(); got != tc.wantErr {
					t.Fatalf("startup error: got %q want %q", got, tc.wantErr)
				}
				if notices != nil {
					t.Fatalf("notices on failure: %v", notices)
				}
				return
			}
			if err != nil {
				t.Fatalf("record must not fail startup: %v", err)
			}
			if _, announced := notices[duplicateTestPath]; announced != tc.wantNotice {
				t.Fatalf("shared path announced = %v, want %v (notices=%v)", announced, tc.wantNotice, notices)
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
			assertNoNotices(t, writeDeprecationRecord(t, tc.entry))
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
