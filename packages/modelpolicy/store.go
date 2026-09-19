package modelpolicy

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/google/uuid"
	"github.com/lib/pq"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

// PolicyLoader loads org model policies from Postgres (or a test fake).
type PolicyLoader interface {
	LoadOrg(ctx context.Context, orgID uuid.UUID) (OrgPolicies, error)
}

// OrgPolicies is a durable epoch + policy snapshot for one org.
type OrgPolicies struct {
	Epoch    uint64
	Policies []Policy
}

// Store loads org_model_policies with RLS org context.
type Store struct {
	db     *sql.DB
	tracer trace.Tracer
}

// NewStore constructs a Store backed by Postgres.
func NewStore(db *sql.DB) (*Store, error) {
	if db == nil {
		return nil, fmt.Errorf("modelpolicy: db is required")
	}
	return &Store{db: db, tracer: otel.Tracer("ibex-modelpolicy")}, nil
}

// LoadOrg returns policies + durable epoch for one org under app.current_org_id RLS.
func (s *Store) LoadOrg(ctx context.Context, orgID uuid.UUID) (OrgPolicies, error) {
	ctx, span := s.tracer.Start(ctx, "Store.LoadOrg",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.operation", "SELECT"),
			attribute.String("org.id", orgID.String()),
		),
	)
	defer span.End()

	out, err := withOrgReadTx(ctx, s.db, orgID, func(tx *sql.Tx) (OrgPolicies, error) {
		epoch, err := scanOrgEpoch(ctx, tx, orgID)
		if err != nil {
			return OrgPolicies{}, err
		}
		policies, err := scanOrgPolicies(ctx, tx, orgID)
		if err != nil {
			return OrgPolicies{}, err
		}
		return OrgPolicies{Epoch: epoch, Policies: policies}, nil
	})
	if err != nil {
		return OrgPolicies{}, recordStoreErr(span, err)
	}
	return out, nil
}

func scanOrgEpoch(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) (uint64, error) {
	var epoch int64
	err := tx.QueryRowContext(ctx, `
		SELECT epoch FROM ibex_core.org_model_policy_meta WHERE org_id = $1`, orgID).Scan(&epoch)
	if err == sql.ErrNoRows {
		// No meta row yet: treat as epoch 1 with empty/loaded policies (deny-by-default).
		return 1, nil
	}
	if err != nil {
		return 0, fmt.Errorf("modelpolicy: epoch: %w", err)
	}
	if epoch < 1 {
		return 0, fmt.Errorf("modelpolicy: invalid epoch %d", epoch)
	}
	return uint64(epoch), nil
}

func withOrgReadTx[T any](
	ctx context.Context,
	db *sql.DB,
	orgID uuid.UUID,
	fn func(*sql.Tx) (T, error),
) (T, error) {
	var zero T
	tx, err := db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return zero, err
	}
	defer func() { _ = tx.Rollback() }()

	if err := setOrgRLS(ctx, tx, orgID); err != nil {
		return zero, err
	}
	out, err := fn(tx)
	if err != nil {
		return zero, err
	}
	if err := tx.Commit(); err != nil {
		return zero, err
	}
	return out, nil
}

func setOrgRLS(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) error {
	_, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgID.String())
	if err != nil {
		return fmt.Errorf("modelpolicy: set rls: %w", err)
	}
	return nil
}

func scanOrgPolicies(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) ([]Policy, error) {
	rows, err := tx.QueryContext(ctx, `
		SELECT id::text, org_id::text, model_pattern, allowed, priority, fallback_chain
		FROM ibex_core.org_model_policies
		WHERE org_id = $1
		ORDER BY priority ASC, model_pattern ASC`, orgID)
	if err != nil {
		return nil, fmt.Errorf("modelpolicy: query: %w", err)
	}
	defer func() { _ = rows.Close() }()

	out := make([]Policy, 0)
	for rows.Next() {
		var p Policy
		var chain pq.StringArray
		if err := rows.Scan(&p.ID, &p.OrgID, &p.Pattern, &p.Allowed, &p.Priority, &chain); err != nil {
			return nil, fmt.Errorf("modelpolicy: scan: %w", err)
		}
		p.FallbackChain = NormalizeFallbackChain([]string(chain))
		out = append(out, p)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

func recordStoreErr(span trace.Span, err error) error {
	span.RecordError(err)
	span.SetStatus(codes.Error, err.Error())
	return err
}
