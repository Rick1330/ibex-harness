package clickhouse

import "strings"

// orderByKeys extracts identifiers from the ORDER BY clause of a SHOW CREATE TABLE.
func orderByKeys(createSQL string) []string {
	upper := strings.ToUpper(createSQL)
	idx := strings.Index(upper, "ORDER BY")
	if idx < 0 {
		return nil
	}
	rest := createSQL[idx+len("ORDER BY"):]
	end := len(rest)
	for _, stop := range []string{"TTL", "SETTINGS", "ENGINE"} {
		if j := strings.Index(strings.ToUpper(rest), stop); j >= 0 && j < end {
			end = j
		}
	}
	clause := rest[:end]
	var keys []string
	for _, part := range strings.Split(clause, ",") {
		tok := strings.TrimSpace(part)
		if tok == "" {
			continue
		}
		fields := strings.Fields(tok)
		if len(fields) == 0 {
			continue
		}
		key := strings.Trim(fields[0], "()`\"")
		if key != "" {
			keys = append(keys, key)
		}
	}
	return keys
}

func orderKeysMatch(got, want []string) bool {
	if len(got) < len(want) {
		return false
	}
	for i, w := range want {
		if !strings.EqualFold(got[i], w) {
			return false
		}
	}
	return true
}
