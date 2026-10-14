//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/canonicaljson"
	"github.com/google/uuid"
)

func TestEvidenceOutboxDigestSchemeDownRewritesJCSRows(t *testing.T) {
	db, dsn := openMigratedSchemaV2DB(t)
	ctx := context.Background()
	orgID := ""
	t.Cleanup(func() {
		if err := Up(dsn); err != nil {
			t.Errorf("restore latest schema: %v", err)
			return
		}
		if orgID != "" {
			if _, err := db.ExecContext(ctx, `DELETE FROM ibex_core.organizations WHERE id = $1`, orgID); err != nil {
				t.Errorf("delete migration test organization: %v", err)
			}
		}
	})

	if err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		var err error
		orgID, err = insertOrg(ctx, tx, "Digest Rollback", "digest-rollback")
		return err
	}); err != nil {
		t.Fatalf("insert organization: %v", err)
	}

	payload := []byte(`{"value": 1}`)
	_, jcsDigest, err := canonicaljson.Digest(payload)
	if err != nil {
		t.Fatalf("calculate JCS digest: %v", err)
	}
	var legacyDigest string
	if err := db.QueryRowContext(ctx, `
		SELECT encode(sha256(convert_to(($1::jsonb)::text, 'UTF8')), 'hex')`, string(payload),
	).Scan(&legacyDigest); err != nil {
		t.Fatalf("calculate legacy digest: %v", err)
	}
	if jcsDigest == legacyDigest {
		t.Fatal("test payload must distinguish JCS and JSONB-text digests")
	}

	jcsID, legacyID := uuid.New(), uuid.New()
	insertMigrationTestOutboxRow(t, db, orgID, jcsID, payload, jcsDigest, "jcs/v1")
	insertMigrationTestOutboxRow(t, db, orgID, legacyID, payload, legacyDigest, "postgres-jsonb-text/v1")

	if err := Down(dsn); err != nil {
		t.Fatalf("down migration 000040: %v", err)
	}
	var convertedDigest string
	if err := db.QueryRowContext(ctx, `
		SELECT payload_digest FROM ibex_core.evidence_outbox WHERE id = $1`, jcsID,
	).Scan(&convertedDigest); err != nil {
		t.Fatalf("read converted JCS row: %v", err)
	}
	if convertedDigest != legacyDigest {
		t.Fatalf("converted digest=%q want legacy digest %q", convertedDigest, legacyDigest)
	}
	var unchangedLegacyDigest string
	if err := db.QueryRowContext(ctx, `
		SELECT payload_digest FROM ibex_core.evidence_outbox WHERE id = $1`, legacyID,
	).Scan(&unchangedLegacyDigest); err != nil {
		t.Fatalf("read legacy row: %v", err)
	}
	if unchangedLegacyDigest != legacyDigest {
		t.Fatalf("legacy digest changed from %q to %q", legacyDigest, unchangedLegacyDigest)
	}

	if err := Up(dsn); err != nil {
		t.Fatalf("reapply migration 000040: %v", err)
	}
	var scheme, remigratedDigest string
	if err := db.QueryRowContext(ctx, `
		SELECT payload_digest_scheme, payload_digest
		FROM ibex_core.evidence_outbox WHERE id = $1`, jcsID,
	).Scan(&scheme, &remigratedDigest); err != nil {
		t.Fatalf("read re-migrated JCS row: %v", err)
	}
	if scheme != "postgres-jsonb-text/v1" {
		t.Fatalf("re-migrated digest scheme=%q want postgres-jsonb-text/v1", scheme)
	}
	if remigratedDigest != legacyDigest {
		t.Fatalf("re-migrated digest=%q want legacy digest %q", remigratedDigest, legacyDigest)
	}
}

func insertMigrationTestOutboxRow(t *testing.T, db *sql.DB, orgID string, id uuid.UUID, payload []byte, digest, scheme string) {
	t.Helper()
	_, err := db.ExecContext(context.Background(), `
		INSERT INTO ibex_core.evidence_outbox (
			id, org_id, event_id, aggregate_id, aggregate_seq, schema_version,
			event_type, payload, payload_digest, payload_digest_scheme
		) VALUES ($1, $2, $3, $4, 1, 'evidence.v1', 'test.digest_rollback', $5::jsonb, $6, $7)`,
		id, orgID, uuid.New(), "digest-rollback-"+id.String(), string(payload), digest, scheme,
	)
	if err != nil {
		t.Fatalf("insert %s outbox row: %v", scheme, err)
	}
}
