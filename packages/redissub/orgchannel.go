package redissub

import (
	"fmt"

	"github.com/google/uuid"
)

// ChannelForOrg returns prefix + org UUID.
func ChannelForOrg(prefix string, orgID uuid.UUID) string {
	return prefix + orgID.String()
}

// ChannelPattern returns the PSUBSCRIBE pattern for a channel prefix.
func ChannelPattern(prefix string) string {
	return prefix + "*"
}

// OrgIDFromChannel extracts the org UUID after prefix.
func OrgIDFromChannel(prefix, channel string) (uuid.UUID, error) {
	if len(channel) <= len(prefix) || channel[:len(prefix)] != prefix {
		return uuid.Nil, fmt.Errorf("redissub: unexpected channel %q", channel)
	}
	return uuid.Parse(channel[len(prefix):])
}
