package billing

import (
	"fmt"

	"github.com/Rick1330/ibex-harness/packages/redissub"
	"github.com/google/uuid"
)

// ChannelPrefix is the Redis pub/sub channel prefix for budget updates.
const ChannelPrefix = "budget_updates:"

// ChannelPattern is the PSUBSCRIBE pattern for all org budget channels.
const ChannelPattern = ChannelPrefix + "*"

// CurrentEventVersion is the InvalidateEvent.Version for this release.
const CurrentEventVersion = 1

var eventPolicy = redissub.EventPolicy{
	ErrPrefix: "billing", CurrentVersion: CurrentEventVersion, RequireEpoch: false,
}

// ChannelForOrg returns the pub/sub channel for one organization.
func ChannelForOrg(orgID uuid.UUID) string {
	return redissub.ChannelForOrg(ChannelPrefix, orgID)
}

// OrgIDFromChannel extracts the org UUID from budget_updates:{org_id}.
func OrgIDFromChannel(channel string) (uuid.UUID, error) {
	id, err := redissub.OrgIDFromChannel(ChannelPrefix, channel)
	if err != nil {
		return uuid.Nil, fmt.Errorf("billing: unexpected channel %q", channel)
	}
	return id, nil
}
