package billing

import (
	"github.com/google/uuid"
)

// ChannelPrefix is the Redis pub/sub channel prefix for budget updates.
const ChannelPrefix = "budget_updates:"

// ChannelPattern is the PSUBSCRIBE pattern for all org budget channels.
const ChannelPattern = ChannelPrefix + "*"

// CurrentEventVersion is the InvalidateEvent.Version for this release.
const CurrentEventVersion = 1

// ChannelForOrg returns the pub/sub channel for one organization.
func ChannelForOrg(orgID uuid.UUID) string {
	return ChannelPrefix + orgID.String()
}

// OrgIDFromChannel extracts the org UUID from budget_updates:{org_id}.
func OrgIDFromChannel(channel string) (uuid.UUID, error) {
	if len(channel) <= len(ChannelPrefix) || channel[:len(ChannelPrefix)] != ChannelPrefix {
		return uuid.Nil, errUnexpectedChannel(channel)
	}
	return uuid.Parse(channel[len(ChannelPrefix):])
}

func errUnexpectedChannel(channel string) error {
	return &channelError{channel: channel}
}

type channelError struct{ channel string }

func (e *channelError) Error() string {
	return "billing: unexpected channel " + e.channel
}
