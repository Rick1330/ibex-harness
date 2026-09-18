package billing

import (
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/redissub"
	"github.com/redis/go-redis/v9"
)

// StartInvalidateSubscriber PSUBSCRIBEs budget_updates:* and invalidates the cache.
// Returns the shared redissub loop handle (Run/Stop/Done).
func StartInvalidateSubscriber(
	client redis.UniversalClient,
	cache redissub.OrgInvalidator,
	log *logger.Logger,
) (*redissub.OrgSubscriber, error) {
	return redissub.NewOrgSubscriber(redissub.OrgSubscriberConfig{
		Client:        client,
		Cache:         cache,
		Log:           log,
		ChannelPrefix: ChannelPrefix,
		ErrPrefix:     "billing",
		Parse: func(payload string) (string, error) {
			ev, err := ParseInvalidateEvent(payload)
			if err != nil {
				return "", err
			}
			return ev.OrgID, nil
		},
		MalformedLog:  "malformed budget update event",
		ChannelBadLog: "budget channel invalid",
		MismatchLog:   "budget event org mismatch",
	})
}
