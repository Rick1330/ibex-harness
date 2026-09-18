package redissub_test

import (
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/redissub"
	"github.com/google/uuid"
)

func TestUnit_OrgInvalidateEvent_Validate(t *testing.T) {
	t.Parallel()
	org := uuid.New().String()
	policy := redissub.EventPolicy{ErrPrefix: "testdomain", CurrentVersion: 1}

	tests := []struct {
		name    string
		event   redissub.OrgInvalidateEvent
		policy  redissub.EventPolicy
		wantErr string
	}{
		{
			name:   "good",
			event:  redissub.OrgInvalidateEvent{Version: 1, OrgID: org, Epoch: 3},
			policy: policy,
		},
		{
			name:    "bad version",
			event:   redissub.OrgInvalidateEvent{Version: 2, OrgID: org},
			policy:  policy,
			wantErr: "testdomain: unsupported event version 2",
		},
		{
			name:    "empty org",
			event:   redissub.OrgInvalidateEvent{Version: 1, OrgID: "  "},
			policy:  policy,
			wantErr: "testdomain: org_id is required",
		},
		{
			name:    "bad uuid",
			event:   redissub.OrgInvalidateEvent{Version: 1, OrgID: "not-a-uuid"},
			policy:  policy,
			wantErr: "testdomain: org_id:",
		},
		{
			name:    "require epoch",
			event:   redissub.OrgInvalidateEvent{Version: 1, OrgID: org, Epoch: 0},
			policy:  redissub.EventPolicy{ErrPrefix: "testdomain", CurrentVersion: 1, RequireEpoch: true},
			wantErr: "testdomain: epoch must be >= 1",
		},
		{
			name:   "default prefix",
			event:  redissub.OrgInvalidateEvent{Version: 99, OrgID: org},
			policy: redissub.EventPolicy{CurrentVersion: 1},
			wantErr: "redissub: unsupported event version 99",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			err := tt.event.Validate(tt.policy)
			if tt.wantErr == "" {
				if err != nil {
					t.Fatalf("Validate: %v", err)
				}
				return
			}
			if err == nil {
				t.Fatal("expected error")
			}
			if !strings.Contains(err.Error(), tt.wantErr) {
				t.Fatalf("err=%q want substring %q", err.Error(), tt.wantErr)
			}
		})
	}
}

func TestUnit_MarshalOrgEvent(t *testing.T) {
	t.Parallel()
	org := uuid.New().String()
	policy := redissub.EventPolicy{ErrPrefix: "testdomain", CurrentVersion: 1}

	tests := []struct {
		name    string
		event   redissub.OrgInvalidateEvent
		wantErr string
		wantSub string
	}{
		{
			name:    "good",
			event:   redissub.OrgInvalidateEvent{Version: 1, OrgID: org, Epoch: 2},
			wantSub: `"org_id":"` + org + `"`,
		},
		{
			name:    "bad version",
			event:   redissub.OrgInvalidateEvent{Version: 0, OrgID: org},
			wantErr: "testdomain: unsupported event version 0",
		},
		{
			name:    "empty org",
			event:   redissub.OrgInvalidateEvent{Version: 1, OrgID: ""},
			wantErr: "testdomain: org_id is required",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got, err := redissub.MarshalOrgEvent(tt.event, policy)
			if tt.wantErr != "" {
				if err == nil {
					t.Fatal("expected error")
				}
				if !strings.Contains(err.Error(), tt.wantErr) {
					t.Fatalf("err=%q want substring %q", err.Error(), tt.wantErr)
				}
				return
			}
			if err != nil {
				t.Fatalf("MarshalOrgEvent: %v", err)
			}
			if !strings.Contains(string(got), tt.wantSub) {
				t.Fatalf("payload=%s want substring %q", got, tt.wantSub)
			}
		})
	}
}

func TestUnit_ParseOrgEvent(t *testing.T) {
	t.Parallel()
	org := uuid.New().String()
	policy := redissub.EventPolicy{ErrPrefix: "testdomain", CurrentVersion: 1, RequireEpoch: true}

	tests := []struct {
		name    string
		payload string
		policy  redissub.EventPolicy
		wantOrg string
		wantErr string
	}{
		{
			name:    "good",
			payload: `{"v":1,"org_id":"` + org + `","epoch":5}`,
			policy:  policy,
			wantOrg: org,
		},
		{
			name:    "bad version",
			payload: `{"v":9,"org_id":"` + org + `","epoch":1}`,
			policy:  policy,
			wantErr: "testdomain: unsupported event version 9",
		},
		{
			name:    "empty org",
			payload: `{"v":1,"org_id":"","epoch":1}`,
			policy:  policy,
			wantErr: "testdomain: org_id is required",
		},
		{
			name:    "bad uuid",
			payload: `{"v":1,"org_id":"abc","epoch":1}`,
			policy:  policy,
			wantErr: "testdomain: org_id:",
		},
		{
			name:    "require epoch",
			payload: `{"v":1,"org_id":"` + org + `"}`,
			policy:  policy,
			wantErr: "testdomain: epoch must be >= 1",
		},
		{
			name:    "decode error",
			payload: `{`,
			policy:  policy,
			wantErr: "testdomain: decode event:",
		},
		{
			name:    "default prefix",
			payload: `{`,
			policy:  redissub.EventPolicy{CurrentVersion: 1},
			wantErr: "redissub: decode event:",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got, err := redissub.ParseOrgEvent(tt.payload, tt.policy)
			if tt.wantErr != "" {
				if err == nil {
					t.Fatal("expected error")
				}
				if !strings.Contains(err.Error(), tt.wantErr) {
					t.Fatalf("err=%q want substring %q", err.Error(), tt.wantErr)
				}
				return
			}
			if err != nil {
				t.Fatalf("ParseOrgEvent: %v", err)
			}
			if got.OrgID != tt.wantOrg {
				t.Fatalf("OrgID=%q want %q", got.OrgID, tt.wantOrg)
			}
		})
	}
}
