package modelpolicy

import (
	"testing"

	"github.com/google/uuid"
)

func TestConfig_ApplyDefaults(t *testing.T) {
	t.Parallel()
	var c Config
	c.ApplyDefaults()
	if c.CacheTTL != defaultCacheTTL || c.LRUSize != defaultLRUSize {
		t.Fatalf("%+v", c)
	}
	if c.AgentDefaultsTTL != defaultAgentDefaultsTTL || c.LoadTimeout != defaultLoadTimeout {
		t.Fatalf("%+v", c)
	}
}

func TestOrgIDFromChannel_RejectsBad(t *testing.T) {
	t.Parallel()
	if _, err := OrgIDFromChannel("directive_updates:x"); err == nil {
		t.Fatal("expected error")
	}
	if _, err := OrgIDFromChannel(ChannelPrefix); err == nil {
		t.Fatal("expected error")
	}
}

func TestInvalidateEvent_MarshalRejectsBad(t *testing.T) {
	t.Parallel()
	_, err := (InvalidateEvent{Version: 99, OrgID: uuid.New().String()}).Marshal()
	if err == nil {
		t.Fatal("expected version error")
	}
}
