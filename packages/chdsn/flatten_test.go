package chdsn

import (
	"net/url"
	"testing"
)

func TestUnit_FlattenUserinfoToQuery_NilSafe(t *testing.T) {
	t.Parallel()

	FlattenUserinfoToQuery(nil)

	u := &url.URL{Scheme: "clickhouse", Host: "localhost:8123"}
	FlattenUserinfoToQuery(u)

	if u.User != nil {
		t.Fatal("expected nil user")
	}
}

func TestUnit_FlattenUserinfoToQuery_MovesCreds(t *testing.T) {
	t.Parallel()

	u, err := url.Parse("clickhouse://default:secret@localhost:8123/ibex")
	if err != nil {
		t.Fatal(err)
	}

	FlattenUserinfoToQuery(u)

	q := u.Query()
	if q.Get("username") != "default" || q.Get("password") != "secret" {
		t.Fatalf("query=%v", q)
	}
	if u.User != nil {
		t.Fatal("userinfo should be cleared")
	}
}

func TestUnit_FlattenUserinfoToQuery_PreservesExistingQueryCreds(t *testing.T) {
	t.Parallel()

	u, err := url.Parse("clickhouse://ignored:ignoredpass@localhost:8123/ibex?username=default&password=ibexdev")
	if err != nil {
		t.Fatal(err)
	}

	FlattenUserinfoToQuery(u)

	q := u.Query()
	if q.Get("username") != "default" || q.Get("password") != "ibexdev" {
		t.Fatalf("query=%v", q)
	}
}
