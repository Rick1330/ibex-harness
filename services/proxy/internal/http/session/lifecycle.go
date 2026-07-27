package session

import (
	"context"
	"strings"

	pkgsession "github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
	"github.com/google/uuid"
)

// StickyExternalID returns a bounded sticky key. Empty or oversized client
// values mint a fresh UUID so every request can still emit X-IBEX-Session-ID.
func StickyExternalID(rawHeader string) string {
	externalID := strings.TrimSpace(rawHeader)
	if externalID == "" || len(externalID) > maxExternalIDLen {
		return uuid.New().String()
	}
	return externalID
}

// Resolve mints/looks up a session. Caller supplies org/agent (never from body).
func (d LifecycleDeps) Resolve(ctx context.Context, in ResolveInput) (*Resolved, error) {
	if d.Store == nil {
		return nil, nil
	}
	if in.OrgID == uuid.Nil || in.AgentID == uuid.Nil {
		return nil, nil
	}
	lookup := sessioncache.LookupKey{
		OrgID: in.OrgID, AgentID: in.AgentID, ExternalID: in.ExternalID,
	}
	if hit, ok := d.cacheLookup(ctx, lookup); ok {
		return hit, nil
	}
	return d.getOrCreateSession(ctx, getOrCreateInput{
		key: lookup, parsed: in.Parsed, providerName: in.ProviderName,
		directiveVID: in.DirectiveVersionID,
	})
}

func (d LifecycleDeps) cacheLookup(
	ctx context.Context,
	key sessioncache.LookupKey,
) (*Resolved, bool) {
	if d.Cache == nil {
		return nil, false
	}
	e, ok := d.Cache.Get(ctx, key)
	if !ok {
		return nil, false
	}
	// Reserve next turn optimistically. Gaps after failed turns are acceptable;
	// ErrDuplicateTurn + retryCheckpoint handles concurrent double-reads.
	d.Cache.Set(ctx, key, sessioncache.Entry{
		SessionID: e.SessionID, TurnCount: e.TurnCount + 1,
	})
	return &Resolved{
		SessionID: e.SessionID, ExternalID: key.ExternalID,
		TurnIndex: e.TurnCount, OrgID: key.OrgID, AgentID: key.AgentID,
	}, true
}

func (d LifecycleDeps) getOrCreateSession(
	ctx context.Context,
	in getOrCreateInput,
) (*Resolved, error) {
	goCtx, cancel := context.WithTimeout(ctx, d.getOrCreateTimeout())
	defer cancel()
	sess, err := d.Store.GetOrCreate(goCtx, in.toParams())
	if err != nil {
		d.warnGetOrCreate(ctx, err)
		return nil, err
	}
	d.cacheSet(ctx, in.key, sessioncache.Entry{
		SessionID: sess.ID, TurnCount: sess.TurnCount + 1,
	})
	return in.toResolved(sess), nil
}

func (in getOrCreateInput) toParams() pkgsession.GetOrCreateParams {
	return pkgsession.GetOrCreateParams{
		OrgID: in.key.OrgID, AgentID: in.key.AgentID, ExternalID: in.key.ExternalID,
		Model: in.parsed.Model, Provider: in.providerName,
		DirectiveVersionID: in.directiveVID,
	}
}

func (in getOrCreateInput) toResolved(sess *pkgsession.Session) *Resolved {
	return &Resolved{
		SessionID: sess.ID, ExternalID: in.key.ExternalID,
		TurnIndex: sess.TurnCount, OrgID: in.key.OrgID, AgentID: in.key.AgentID,
	}
}

func (d LifecycleDeps) cacheSet(
	ctx context.Context,
	key sessioncache.LookupKey,
	entry sessioncache.Entry,
) {
	if d.Cache == nil {
		return
	}
	d.Cache.Set(ctx, key, entry)
}

func (d LifecycleDeps) warnGetOrCreate(ctx context.Context, err error) {
	if d.Log == nil {
		return
	}
	d.Log.WarnCtx(ctx, "session get_or_create failed; continuing without session",
		"error", err.Error())
}
