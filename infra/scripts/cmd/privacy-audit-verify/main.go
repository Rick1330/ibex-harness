// Command privacy-audit-verify walks privacy_audit_ledger per org and exits
// non-zero on the first hash-chain break (milestone 4.P.3).
// Layout matches other utility CLIs under infra/scripts/cmd/.
package main

import (
	"context"
	"database/sql"
	"flag"
	"fmt"
	"os"

	"github.com/Rick1330/ibex-harness/packages/privacyaudit"
	_ "github.com/lib/pq"
)

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	fs := flag.NewFlagSet("privacy-audit-verify", flag.ContinueOnError)
	fs.SetOutput(os.Stderr)
	dsn := fs.String("dsn", os.Getenv("POSTGRES_DSN"), "Postgres DSN")
	orgFlag := fs.String("org", "", "optional org UUID (default: all orgs with ledger rows)")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *dsn == "" {
		fmt.Fprintln(os.Stderr, "privacy-audit-verify: -dsn or POSTGRES_DSN required")
		return 2
	}
	return verifyDSN(*dsn, *orgFlag)
}

func verifyDSN(dsn, orgFilter string) int {
	db, err := openPostgres(dsn)
	if err != nil {
		fmt.Fprintf(os.Stderr, "open: %v\n", err)
		return 2
	}
	defer db.Close()
	return verifyDB(context.Background(), db, orgFilter)
}

func openPostgres(dsn string) (*sql.DB, error) {
	return sql.Open("postgres", dsn)
}

func verifyDB(ctx context.Context, db *sql.DB, orgFilter string) int {
	orgs, err := ResolveOrgs(ctx, db, orgFilter)
	if err != nil {
		fmt.Fprintf(os.Stderr, "list orgs: %v\n", err)
		return 2
	}
	for _, org := range orgs {
		n, verr := VerifyOrg(ctx, db, org)
		if verr != nil {
			fmt.Fprintf(os.Stderr, "VERIFY FAIL org=%s idx=%d: %v\n", org, privacyaudit.BreakIndex(verr), verr)
			return 1
		}
		fmt.Printf("ok org=%s rows=%d\n", org, n)
	}
	return 0
}
