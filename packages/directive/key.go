package directive

import (
	"fmt"

	"github.com/google/uuid"
)

// CacheKey returns the org-scoped Redis key for an agent's directive.
// Format: {org_id}:directive:{agent_id}
func CacheKey(orgID, agentID uuid.UUID) string {
	return fmt.Sprintf("%s:directive:%s", orgID.String(), agentID.String())
}

func cacheKey(orgID, agentID uuid.UUID) string {
	return CacheKey(orgID, agentID)
}

// ChannelPrefix is the Redis pub/sub channel prefix for directive updates.
// Full channel: directive_updates:{org_id} (tenant-scoped fan-out).
const ChannelPrefix = "directive_updates:"

// ChannelPattern is the PSUBSCRIBE pattern for all org directive channels.
const ChannelPattern = ChannelPrefix + "*"

// ChannelForOrg returns the pub/sub channel for one organization.
func ChannelForOrg(orgID uuid.UUID) string {
	return ChannelPrefix + orgID.String()
}

// OrgIDFromChannel extracts the org UUID from a directive_updates:{org_id} channel.
// Returns an error when the channel prefix is wrong or the UUID is malformed.
func OrgIDFromChannel(channel string) (uuid.UUID, error) {
	if len(channel) <= len(ChannelPrefix) || channel[:len(ChannelPrefix)] != ChannelPrefix {
		return uuid.Nil, fmt.Errorf("directive: unexpected channel %q", channel)
	}
	return uuid.Parse(channel[len(ChannelPrefix):])
}
