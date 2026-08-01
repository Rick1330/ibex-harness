package config

import (
	"reflect"
	"testing"
)

func TestUnit_ParseCSVModels(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		in   string
		want []string
	}{
		{
			name: "populated_dedupe_trim",
			in:   " openai/gpt-oss-20b:free , gpt-4o, ,openai/gpt-oss-20b:free ",
			want: []string{"openai/gpt-oss-20b:free", "gpt-4o"},
		},
		{
			name: "empty",
			in:   "",
			want: []string{},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			got := parseCSVModels(tc.in)

			if len(got) != len(tc.want) {
				t.Fatalf("len=%d want %d got=%v", len(got), len(tc.want), got)
			}
			if len(tc.want) == 0 {
				return
			}
			if !reflect.DeepEqual(got, tc.want) {
				t.Fatalf("got=%v want=%v", got, tc.want)
			}
		})
	}
}
