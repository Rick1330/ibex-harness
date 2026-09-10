package ratelimit

import (
	"fmt"

	"github.com/google/uuid"
)

// ChannelPrefix is the Redis pub/sub channel prefix for rate-limit config updates.
// Full channel: ratelimit_config_updates:{org_id}
const ChannelPrefix = "ratelimit_config_updates:"

// ChannelPattern is the PSUBSCRIBE pattern for all org rate-limit config channels.
const ChannelPattern = ChannelPrefix + "*"

// ChannelForOrg returns the pub/sub channel for one organization's rate-limit config.
func ChannelForOrg(orgID uuid.UUID) string {
	return ChannelPrefix + orgID.String()
}

// OrgIDFromChannel extracts the org UUID from ratelimit_config_updates:{org_id}.
func OrgIDFromChannel(channel string) (uuid.UUID, error) {
	if len(channel) <= len(ChannelPrefix) || channel[:len(ChannelPrefix)] != ChannelPrefix {
		return uuid.Nil, fmt.Errorf("ratelimit: unexpected channel %q", channel)
	}
	return uuid.Parse(channel[len(ChannelPrefix):])
}
