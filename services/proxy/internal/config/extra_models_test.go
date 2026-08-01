package config

import (
	"testing"
)

func TestUnit_ParseCSVModels(t *testing.T) {
	t.Parallel()
	got := parseCSVModels(" openai/gpt-oss-20b:free , gpt-4o, ,openai/gpt-oss-20b:free ")
	if len(got) != 2 {
		t.Fatalf("got=%v", got)
	}
	if got[0] != "openai/gpt-oss-20b:free" || got[1] != "gpt-4o" {
		t.Fatalf("got=%v", got)
	}
	if parseCSVModels("") != nil && len(parseCSVModels("")) != 0 {
		t.Fatalf("empty should be empty slice")
	}
}
