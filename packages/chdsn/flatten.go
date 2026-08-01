// Package chdsn holds ClickHouse DSN helpers shared by migrate and app clients
// without importing clickhouse-go (avoids database/sql driver double-register).
package chdsn

import "net/url"

// FlattenUserinfoToQuery moves user:pass into username=/password= query params.
// clickhouse-go authenticates reliably with query credentials but not URL userinfo.
func FlattenUserinfoToQuery(u *url.URL) {
	if u == nil || u.User == nil {
		return
	}
	user := u.User.Username()
	pass, hasPass := u.User.Password()
	q := u.Query()
	if user != "" && q.Get("username") == "" {
		q.Set("username", user)
	}
	if hasPass && q.Get("password") == "" {
		q.Set("password", pass)
	}
	u.User = nil
	u.RawQuery = q.Encode()
}
