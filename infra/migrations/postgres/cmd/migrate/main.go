package main

import (
	"flag"
	"fmt"
	"os"

	pgmigrate "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
)

func main() {
	command := flag.String("command", "", "migration command: up, down, version, force")
	version := flag.Int("version", 0, "target version for force")
	flag.Parse()

	if *command == "" && flag.NArg() > 0 {
		*command = flag.Arg(0)
	}
	if *command == "" {
		fmt.Fprintln(os.Stderr, "usage: migrate -command up|down|version|force [-version N]")
		os.Exit(2)
	}

	dsn := pgmigrate.ResolveDSN()

	switch *command {
	case "up":
		if err := pgmigrate.Up(dsn); err != nil {
			fmt.Fprintf(os.Stderr, "migrate up: %v\n", err)
			os.Exit(1)
		}
		fmt.Println("migrate up: ok")
	case "down":
		if err := pgmigrate.Down(dsn); err != nil {
			fmt.Fprintf(os.Stderr, "migrate down: %v\n", err)
			os.Exit(1)
		}
		fmt.Println("migrate down: ok")
	case "version":
		v, dirty, err := pgmigrate.Version(dsn)
		if err != nil {
			fmt.Fprintf(os.Stderr, "migrate version: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("version=%d dirty=%v\n", v, dirty)
	case "force":
		if *version <= 0 {
			fmt.Fprintln(os.Stderr, "migrate force requires -version N")
			os.Exit(2)
		}
		if err := pgmigrate.Force(dsn, *version); err != nil {
			fmt.Fprintf(os.Stderr, "migrate force: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("migrate force: ok (version=%d)\n", *version)
	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n", *command)
		os.Exit(2)
	}
}
