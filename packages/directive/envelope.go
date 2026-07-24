package directive

import (
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
)

// CurrentEnvelopeVersion is the cache envelope schema version.
const CurrentEnvelopeVersion = 1

// DefaultInjectionMode matches directives.injection_mode DEFAULT.
const DefaultInjectionMode = "system_first"

// envelope is the typed Redis cache value.
type envelope struct {
	Version       int    `json:"v"`
	Content       string `json:"content"`
	InjectionMode string `json:"injection_mode"`
	VersionID     string `json:"version_id,omitempty"`
}

func marshalEnvelope(r Resolved) ([]byte, error) {
	e := envelope{
		Version:       CurrentEnvelopeVersion,
		Content:       r.Content,
		InjectionMode: r.InjectionMode,
	}
	if r.VersionID != uuid.Nil {
		e.VersionID = r.VersionID.String()
	}
	if e.InjectionMode == "" && e.Content != "" {
		e.InjectionMode = DefaultInjectionMode
	}
	return json.Marshal(e)
}

func unmarshalEnvelope(raw []byte) (Resolved, error) {
	var e envelope
	if err := json.Unmarshal(raw, &e); err != nil {
		return Resolved{}, fmt.Errorf("directive: decode envelope: %w", err)
	}
	if e.Version != CurrentEnvelopeVersion {
		return Resolved{}, fmt.Errorf("directive: unsupported envelope version %d", e.Version)
	}
	out := Resolved{Content: e.Content, InjectionMode: e.InjectionMode}
	if e.VersionID == "" {
		return out, nil
	}
	id, err := uuid.Parse(e.VersionID)
	if err != nil {
		return Resolved{}, fmt.Errorf("directive: version_id: %w", err)
	}
	out.VersionID = id
	return out, nil
}
