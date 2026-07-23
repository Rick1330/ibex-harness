package config

import (
	"testing"
	"time"
)

func TestParseEnabledFlag(t *testing.T) {
	t.Parallel()
	cases := []struct {
		raw     string
		def     bool
		want    bool
		wantErr bool
	}{
		{raw: "", def: true, want: true},
		{raw: "true", want: true},
		{raw: "FALSE", want: false},
		{raw: "1", want: true},
		{raw: "0", want: false},
		{raw: "yes", want: true},
		{raw: "no", want: false},
		{raw: "maybe", wantErr: true},
	}
	for _, tc := range cases {
		got, err := parseEnabledFlag(tc.raw, tc.def)
		if tc.wantErr {
			if err == nil {
				t.Fatalf("%q: expected error", tc.raw)
			}
			continue
		}
		if err != nil || got != tc.want {
			t.Fatalf("%q: got=%v err=%v want=%v", tc.raw, got, err, tc.want)
		}
	}
}

func TestApplyAuthCacheEnv(t *testing.T) {
	t.Parallel()
	cfg := &Config{}
	err := applyAuthCacheEnv(cfg, envConfig{
		AuthCacheEnabled:     "false",
		AuthCacheLRUCapacity: 100,
		AuthCacheLRUMaxTTL:   5 * time.Second,
		AuthCacheBloomItems:  50,
		AuthCacheBloomFPRate: 0.01,
	})
	if err != nil {
		t.Fatal(err)
	}
	if cfg.AuthCache.Enabled {
		t.Fatal("expected disabled")
	}
	if cfg.AuthCache.LRUCapacity != 100 || cfg.AuthCache.BloomExpectedItems != 50 {
		t.Fatalf("%+v", cfg.AuthCache)
	}
	if cfg.AuthCache.LRUMaxTTL != 5*time.Second || cfg.AuthCache.BloomFPRate != 0.01 {
		t.Fatalf("%+v", cfg.AuthCache)
	}
}

func TestApplyAuthCacheDefaults(t *testing.T) {
	t.Parallel()
	var cfg Config
	cfg.applyAuthCacheDefaults()
	if cfg.AuthCache.LRUCapacity != 5000 || cfg.AuthCache.BloomExpectedItems != 10000 {
		t.Fatalf("%+v", cfg.AuthCache)
	}
}
