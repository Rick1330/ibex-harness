package clickhouse

import "strings"

// orderByKeys extracts identifiers from the ORDER BY clause of a SHOW CREATE TABLE.
func orderByKeys(createSQL string) []string {
	clause, ok := extractOrderByClause(createSQL)
	if !ok {
		return nil
	}
	return parseOrderByKeyList(clause)
}

func extractOrderByClause(createSQL string) (string, bool) {
	upper := strings.ToUpper(createSQL)
	idx := strings.Index(upper, "ORDER BY")
	if idx < 0 {
		return "", false
	}
	rest := createSQL[idx+len("ORDER BY"):]
	end := orderByClauseEnd(rest)
	return rest[:end], true
}

func orderByClauseEnd(rest string) int {
	end := len(rest)
	upper := strings.ToUpper(rest)
	for _, stop := range []string{"TTL", "SETTINGS", "ENGINE"} {
		if j := strings.Index(upper, stop); j >= 0 && j < end {
			end = j
		}
	}
	return end
}

func parseOrderByKeyList(clause string) []string {
	var keys []string
	for _, part := range strings.Split(clause, ",") {
		if key := orderByTokenKey(part); key != "" {
			keys = append(keys, key)
		}
	}
	return keys
}

func orderByTokenKey(part string) string {
	tok := strings.TrimSpace(part)
	if tok == "" {
		return ""
	}
	fields := strings.Fields(tok)
	if len(fields) == 0 {
		return ""
	}
	return strings.Trim(fields[0], "()`\"")
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
