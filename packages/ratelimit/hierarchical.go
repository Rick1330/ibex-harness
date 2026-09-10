package ratelimit

import (
	"context"
	"fmt"
	"strconv"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

const (
	defaultGlobalRPM     = 100_000
	tierAgent            = "agent"
	tierOrg              = "org"
	tierGlobal           = "global"
	hierarchicalAgentOff = "0"
	hierarchicalAgentOn  = "1"
)

// hierarchicalLua admits agent → org → global with INCR-then-compare.
// EXPIRE only when a key is first created (ARGV[4] = TTL seconds).
// On org/global deny, rolls back inner increments so outer budgets are not burned.
//
// KEYS[1]=agent (unused when disabled), KEYS[2]=org, KEYS[3]=global
// ARGV[1]=agent_limit, ARGV[2]=org_limit, ARGV[3]=global_limit, ARGV[4]=ttl_sec, ARGV[5]=agent_enabled ("0"|"1")
// Returns: {allowed (0|1), tier, org_count, org_limit}
var hierarchicalLua = redis.NewScript(`
local agent_enabled = ARGV[5] == "1"
local agent_limit = tonumber(ARGV[1])
local org_limit = tonumber(ARGV[2])
local global_limit = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local function incr_expire(key)
  local n = redis.call("INCR", key)
  if n == 1 then
    redis.call("EXPIRE", key, ttl)
  end
  return n
end

local function org_get()
  return tonumber(redis.call("GET", KEYS[2]) or "0")
end

if agent_enabled then
  local agent_count = incr_expire(KEYS[1])
  if agent_count > agent_limit then
    return {0, "agent", org_get(), org_limit}
  end
end

local org_count = incr_expire(KEYS[2])
if org_count > org_limit then
  if agent_enabled then
    redis.call("DECR", KEYS[1])
  end
  return {0, "org", org_count, org_limit}
end

local global_count = incr_expire(KEYS[3])
if global_count > global_limit then
  if agent_enabled then
    redis.call("DECR", KEYS[1])
  end
  redis.call("DECR", KEYS[2])
  return {0, "global", org_count - 1, org_limit}
end

return {1, "", org_count, org_limit}
`)

// HierarchicalConfig configures agent → org → global per-minute RPM limits.
// Agent RPM equals DefaultRPM (per-agent overrides are 4.B.2).
type HierarchicalConfig struct {
	DefaultRPM   int64
	OrgOverrides map[uuid.UUID]int64
	GlobalRPM    int64
}

// HierarchicalLimiter implements Limiter with one atomic Lua round trip.
type HierarchicalLimiter struct {
	client redis.UniversalClient
	cfg    HierarchicalConfig
}

// NewHierarchicalLimiter returns a hierarchical RPM limiter backed by Redis.
func NewHierarchicalLimiter(client redis.UniversalClient, cfg HierarchicalConfig) (Limiter, error) {
	if client == nil {
		return nil, ErrNilClient
	}
	if cfg.DefaultRPM < 1 {
		cfg.DefaultRPM = 60
	}
	if cfg.GlobalRPM < 1 {
		cfg.GlobalRPM = defaultGlobalRPM
	}
	return &HierarchicalLimiter{client: client, cfg: cfg}, nil
}

// Check enforces agent → org → global budgets for the current UTC minute.
// A nil agentID skips the agent tier (org + global only).
func (h *HierarchicalLimiter) Check(ctx context.Context, orgID, agentID uuid.UUID) (Result, error) {
	orgLimit := h.effectiveOrgLimit(orgID)
	agentLimit := h.cfg.DefaultRPM
	globalLimit := h.cfg.GlobalRPM
	window := currentMinuteWindow(time.Now().UTC())

	orgKey := orgRPMKey(orgID, window.unixMinute)
	globalKey := globalRPMKey(window.unixMinute)
	agentKey := ""
	agentEnabled := hierarchicalAgentOff
	if agentID != uuid.Nil {
		agentKey = agentRPMKey(orgID, agentID, window.unixMinute)
		agentEnabled = hierarchicalAgentOn
	}

	raw, err := hierarchicalLua.Run(ctx, h.client,
		[]string{agentKey, orgKey, globalKey},
		agentLimit, orgLimit, globalLimit, int(keyTTL.Seconds()), agentEnabled,
	).Slice()
	if err != nil {
		return Result{}, fmt.Errorf("HierarchicalLimiter.Check orgID=%s: %w", orgID.String(), err)
	}
	return resultFromHierarchical(raw, orgLimit, window)
}

func (h *HierarchicalLimiter) effectiveOrgLimit(orgID uuid.UUID) int64 {
	if rpm, ok := h.cfg.OrgOverrides[orgID]; ok && rpm > 0 {
		return rpm
	}
	return h.cfg.DefaultRPM
}

func orgRPMKey(orgID uuid.UUID, unixMinute int64) string {
	return fmt.Sprintf("ratelimit:%s:rpm:%d", orgID.String(), unixMinute)
}

func agentRPMKey(orgID, agentID uuid.UUID, unixMinute int64) string {
	return fmt.Sprintf("ratelimit:%s:agent:%s:rpm:%d", orgID.String(), agentID.String(), unixMinute)
}

func globalRPMKey(unixMinute int64) string {
	return fmt.Sprintf("ratelimit:global:rpm:%d", unixMinute)
}

func resultFromHierarchical(raw []any, orgLimit int64, window minuteWindow) (Result, error) {
	if len(raw) < 4 {
		return Result{}, fmt.Errorf("hierarchical lua: want 4 values, got %d", len(raw))
	}
	allowedN, err := asInt64(raw[0])
	if err != nil {
		return Result{}, fmt.Errorf("hierarchical lua allowed: %w", err)
	}
	tier := asString(raw[1])
	orgCount, err := asInt64(raw[2])
	if err != nil {
		return Result{}, fmt.Errorf("hierarchical lua org_count: %w", err)
	}
	limit, err := asInt64(raw[3])
	if err != nil {
		return Result{}, fmt.Errorf("hierarchical lua org_limit: %w", err)
	}
	if limit < 1 {
		limit = orgLimit
	}
	res := resultFromCount(orgCount, limit, window)
	if allowedN == 0 {
		res.Allowed = false
		res.Remaining = 0
		res.RetryAfter = window.retryAfter
		res.DeniedTier = tier
		if res.DeniedTier == "" {
			res.DeniedTier = tierOrg
		}
	}
	return res, nil
}

func asString(v any) string {
	switch s := v.(type) {
	case string:
		return s
	case []byte:
		return string(s)
	default:
		return fmt.Sprint(v)
	}
}

func asInt64(v any) (int64, error) {
	switch n := v.(type) {
	case int64:
		return n, nil
	case int:
		return int64(n), nil
	case string:
		return strconv.ParseInt(n, 10, 64)
	case []byte:
		return strconv.ParseInt(string(n), 10, 64)
	default:
		return 0, fmt.Errorf("unexpected type %T", v)
	}
}
