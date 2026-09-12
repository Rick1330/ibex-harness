package modelpolicy

import (
	"fmt"

	"github.com/google/uuid"
)

// ChannelPrefix is the Redis pub/sub channel prefix for model-policy updates.
const ChannelPrefix = "model_policy_updates:"

// ChannelPattern is the PSUBSCRIBE pattern for all org model-policy channels.
const ChannelPattern = ChannelPrefix + "*"

// CurrentEventVersion is the InvalidateEvent.Version for this release.
const CurrentEventVersion = 1

// ChannelForOrg returns the pub/sub channel for one organization.
func ChannelForOrg(orgID uuid.UUID) string {
	return ChannelPrefix + orgID.String()
}

// OrgIDFromChannel extracts the org UUID from model_policy_updates:{org_id}.
func OrgIDFromChannel(channel string) (uuid.UUID, error) {
	if len(channel) <= len(ChannelPrefix) || channel[:len(ChannelPrefix)] != ChannelPrefix {
		return uuid.Nil, fmt.Errorf("modelpolicy: unexpected channel %q", channel)
	}
	return uuid.Parse(channel[len(ChannelPrefix):])
}
