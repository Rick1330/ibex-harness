package postgres

import (
	"crypto/sha256"
	"encoding/hex"
	"os"
	"sort"
	"strconv"
	"strings"
	"testing"
)

const (
	// releasedV019Manifest pins the migration files as they existed at tag
	// v0.1.9: one "<sha256>  <basename>" line per .sql file, generated from the
	// tag with `git show v0.1.9:<path>`, never from the working tree.
	releasedV019Manifest = "testdata/released/v0.1.9.sha256"
	// releasedV019Version is the last migration version that tag contains.
	releasedV019Version = 39
)

// releasedFile is one pinned migration file: its basename and expected digest.
type releasedFile struct {
	name string
	sum  string
}

// TestUnit_ReleasedMigrationSetImmutable proves the upgrade rehearsal rehearses
// the released schema and not whatever the working tree happens to contain.
//
// Every .sql file at tag v0.1.9 is byte-identical on main (the tag-to-main diff
// adds files and touches only Go), so applying migrations 1..39 from this
// checkout is the v0.1.9 schema by construction. That construction is only true
// while the released files stay byte-identical, which is what this test pins.
func TestUnit_ReleasedMigrationSetImmutable(t *testing.T) {
	pinned := readReleasedManifest(t)
	entries := embeddedMigrationEntries(t)
	assertPinnedFilesUnchanged(t, pinned)
	assertReleasedNamesMatch(t, entries, pinned)
	assertReleasedVersionsContiguous(t, entries, releasedV019Version)
}

// readReleasedManifest parses the pinned "<sha256>  <basename>" lines.
func readReleasedManifest(t *testing.T) []releasedFile {
	t.Helper()
	raw, err := os.ReadFile(releasedV019Manifest)
	if err != nil {
		t.Fatalf("read released manifest: %v", err)
	}
	var files []releasedFile
	for _, line := range strings.Split(strings.TrimSpace(string(raw)), "\n") {
		if line != "" {
			files = append(files, parseReleasedLine(t, line))
		}
	}
	if len(files) == 0 {
		t.Fatalf("released manifest %s is empty", releasedV019Manifest)
	}
	return files
}

// parseReleasedLine splits one manifest line into its digest and basename.
func parseReleasedLine(t *testing.T, line string) releasedFile {
	t.Helper()
	fields := strings.SplitN(line, "  ", 2)
	if len(fields) != 2 || len(fields[0]) != sha256.Size*2 {
		t.Fatalf("malformed released manifest line %q", line)
	}
	return releasedFile{name: fields[1], sum: fields[0]}
}

// embeddedMigrationEntries lists the embedded migration files.
func embeddedMigrationEntries(t *testing.T) []os.DirEntry {
	t.Helper()
	entries, err := migrationFiles.ReadDir(".")
	if err != nil {
		t.Fatalf("read migrations: %v", err)
	}
	return entries
}

// assertPinnedFilesUnchanged requires every pinned file to exist in the embedded
// set with the digest recorded at the tag, naming the file that moved.
func assertPinnedFilesUnchanged(t *testing.T, pinned []releasedFile) {
	t.Helper()
	for _, want := range pinned {
		body, err := migrationFiles.ReadFile(want.name)
		if err != nil {
			t.Errorf("released migration %s is missing from the embedded set: %v", want.name, err)
			continue
		}
		sum := sha256.Sum256(body)
		if got := hex.EncodeToString(sum[:]); got != want.sum {
			t.Errorf("released migration %s was modified: sha256 %s, want %s", want.name, got, want.sum)
		}
	}
}

// assertReleasedNamesMatch requires the embedded set at or below the released
// version to equal the pinned name set in both directions, which rules out an
// addition, a removal, and a renumbering.
func assertReleasedNamesMatch(t *testing.T, entries []os.DirEntry, pinned []releasedFile) {
	t.Helper()
	want := pinnedNameSet(pinned)
	got := embeddedNameSet(entries, releasedV019Version)
	for _, name := range namesAbsentFrom(want, got) {
		t.Errorf("migration %s existed at v0.1.9 but is missing from the embedded set", name)
	}
	for _, name := range namesAbsentFrom(got, want) {
		t.Errorf("migration %s is embedded at or below v%d but did not exist at v0.1.9", name, releasedV019Version)
	}
}

// namesAbsentFrom returns every name present in want and absent from got, so
// each direction of the set comparison is one named property rather than a
// conditional nested inside a loop.
func namesAbsentFrom(want, got map[string]bool) []string {
	var absent []string
	for name := range want {
		if !got[name] {
			absent = append(absent, name)
		}
	}
	return absent
}

// pinnedNameSet collects the basenames the manifest pins.
func pinnedNameSet(pinned []releasedFile) map[string]bool {
	set := make(map[string]bool, len(pinned))
	for _, file := range pinned {
		set[file.name] = true
	}
	return set
}

// embeddedNameSet collects every embedded .sql basename whose version prefix is
// at most maxVersion.
func embeddedNameSet(entries []os.DirEntry, maxVersion int) map[string]bool {
	set := make(map[string]bool)
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".sql") {
			continue
		}
		if version, ok := nameVersion(entry.Name()); ok && version <= maxVersion {
			set[entry.Name()] = true
		}
	}
	return set
}

// nameVersion parses the numeric prefix every migration filename starts with.
func nameVersion(name string) (int, bool) {
	idx := strings.IndexByte(name, '_')
	if idx <= 0 {
		return 0, false
	}
	version, err := strconv.Atoi(name[:idx])
	if err != nil {
		return 0, false
	}
	return version, true
}

// assertReleasedVersionsContiguous requires the released span to end exactly at
// last and to contain every version from 1 to last. TestMigrationFileNaming's
// strictly-increasing check does not catch a gap, so 1..38 followed by 40 would
// pass it while silently skipping 39.
func assertReleasedVersionsContiguous(t *testing.T, entries []os.DirEntry, last int) {
	t.Helper()
	versions := embeddedUpVersions(entries, last)
	if len(versions) == 0 {
		t.Fatalf("no up migrations at or below v%d", last)
	}
	if newest := versions[len(versions)-1]; newest != last {
		t.Fatalf("newest released up migration is v%d, want v%d", newest, last)
	}
	for i, version := range versions {
		if version != i+1 {
			t.Fatalf("released migration versions have a gap: position %d holds v%d, want v%d", i, version, i+1)
		}
	}
}

// embeddedUpVersions returns the sorted up-migration versions at or below
// maxVersion.
func embeddedUpVersions(entries []os.DirEntry, maxVersion int) []int {
	var versions []int
	for _, entry := range entries {
		match := upMigrationPattern.FindStringSubmatch(entry.Name())
		if match == nil {
			continue
		}
		if version, err := strconv.Atoi(match[1]); err == nil && version <= maxVersion {
			versions = append(versions, version)
		}
	}
	sort.Ints(versions)
	return versions
}
