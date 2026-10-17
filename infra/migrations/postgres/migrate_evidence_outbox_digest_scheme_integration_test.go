//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/canonicaljson"
	"github.com/google/uuid"
)

type outboxDigestMigrationFixture struct {
	db           *sql.DB
	dsn          string
	ctx          context.Context
	orgID        string
	payload      []byte
	jcsID        uuid.UUID
	legacyID     uuid.UUID
	jcsDigest    string
	legacyDigest string
}

type migrationOutboxDigestRow struct {
	id     uuid.UUID
	digest string
	scheme string
}

func TestEvidenceOutboxDigestSchemeDownRewritesJCSRows(t *testing.T) {
	fixture := newOutboxDigestMigrationFixture(t)
	fixture.insertRows(t)
	fixture.rollback(t)
	fixture.assertLegacyDigests(t)
	fixture.reapplyAndAssert(t)
}

func newOutboxDigestMigrationFixture(t *testing.T) *outboxDigestMigrationFixture {
	db, dsn := openMigratedSchemaV2DB(t)
	fixture := &outboxDigestMigrationFixture{
		db: db, dsn: dsn, ctx: context.Background(),
		payload: []byte(`{"value": 1}`), jcsID: uuid.New(), legacyID: uuid.New(),
	}
	t.Cleanup(func() { fixture.cleanup(t) })
	fixture.createOrganization(t)
	fixture.calculateDigests(t)
	return fixture
}

func (f *outboxDigestMigrationFixture) createOrganization(t *testing.T) {
	err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		var err error
		f.orgID, err = insertOrg(f.ctx, tx, "Digest Rollback", "digest-rollback")
		return err
	})
	if err != nil {
		t.Fatalf("insert organization: %v", err)
	}
}

func (f *outboxDigestMigrationFixture) calculateDigests(t *testing.T) {
	var err error
	_, f.jcsDigest, err = canonicaljson.Digest(f.payload)
	if err != nil {
		t.Fatalf("calculate JCS digest: %v", err)
	}
	err = f.db.QueryRowContext(f.ctx, `
		SELECT encode(sha256(convert_to(($1::jsonb)::text, 'UTF8')), 'hex')`, string(f.payload),
	).Scan(&f.legacyDigest)
	if err != nil {
		t.Fatalf("calculate legacy digest: %v", err)
	}
	if f.jcsDigest == f.legacyDigest {
		t.Fatal("test payload must distinguish JCS and JSONB-text digests")
	}
}

func (f *outboxDigestMigrationFixture) insertRows(t *testing.T) {
	f.insertRow(t, migrationOutboxDigestRow{id: f.jcsID, digest: f.jcsDigest, scheme: "jcs/v1"})
	f.insertRow(t, migrationOutboxDigestRow{id: f.legacyID, digest: f.legacyDigest, scheme: "postgres-jsonb-text/v1"})
}

func (f *outboxDigestMigrationFixture) insertRow(t *testing.T, row migrationOutboxDigestRow) {
	t.Helper()
	_, err := f.db.ExecContext(f.ctx, `
		INSERT INTO ibex_core.evidence_outbox (
			id, org_id, event_id, aggregate_id, aggregate_seq, schema_version,
			event_type, payload, payload_digest, payload_digest_scheme
		) VALUES ($1, $2, $3, $4, 1, 'evidence.v1', 'test.digest_rollback', $5::jsonb, $6, $7)`,
		row.id, f.orgID, uuid.New(), "digest-rollback-"+row.id.String(), string(f.payload), row.digest, row.scheme,
	)
	if err != nil {
		t.Fatalf("insert %s outbox row: %v", row.scheme, err)
	}
}

func (f *outboxDigestMigrationFixture) rollback(t *testing.T) {
	version, dirty, err := Version(f.dsn)
	if err != nil || dirty {
		t.Fatalf("read current migration version before rollback: version=%d dirty=%v err=%v", version, dirty, err)
	}
	if version < 40 {
		t.Fatalf("schema version=%d; need migration 000040 applied", version)
	}
	for version >= 40 {
		if err := Down(f.dsn); err != nil {
			t.Fatalf("roll back migration %d: %v", version, err)
		}
		version, dirty, err = Version(f.dsn)
		if err != nil || dirty {
			t.Fatalf("read migration version after rollback: version=%d dirty=%v err=%v", version, dirty, err)
		}
	}
}

func (f *outboxDigestMigrationFixture) assertLegacyDigests(t *testing.T) {
	f.assertRowDigest(t, f.jcsID, f.legacyDigest)
	f.assertRowDigest(t, f.legacyID, f.legacyDigest)
}

func (f *outboxDigestMigrationFixture) assertRowDigest(t *testing.T, id uuid.UUID, want string) {
	var got string
	if err := f.db.QueryRowContext(f.ctx, `
		SELECT payload_digest FROM ibex_core.evidence_outbox WHERE id = $1`, id,
	).Scan(&got); err != nil {
		t.Fatalf("read digest for %s: %v", id, err)
	}
	if got != want {
		t.Fatalf("digest for %s=%q want %q", id, got, want)
	}
}

func (f *outboxDigestMigrationFixture) reapplyAndAssert(t *testing.T) {
	if err := Up(f.dsn); err != nil {
		t.Fatalf("reapply migration 000040: %v", err)
	}
	var scheme string
	if err := f.db.QueryRowContext(f.ctx, `
		SELECT payload_digest_scheme FROM ibex_core.evidence_outbox WHERE id = $1`, f.jcsID,
	).Scan(&scheme); err != nil {
		t.Fatalf("read re-migrated scheme: %v", err)
	}
	if scheme != "postgres-jsonb-text/v1" {
		t.Fatalf("re-migrated digest scheme=%q want postgres-jsonb-text/v1", scheme)
	}
	f.assertRowDigest(t, f.jcsID, f.legacyDigest)
}

func (f *outboxDigestMigrationFixture) cleanup(t *testing.T) {
	if err := Up(f.dsn); err != nil {
		t.Errorf("restore latest schema: %v", err)
		return
	}
	if f.orgID != "" {
		if _, err := f.db.ExecContext(f.ctx, `DELETE FROM ibex_core.organizations WHERE id = $1`, f.orgID); err != nil {
			t.Errorf("delete migration test organization: %v", err)
		}
	}
}
