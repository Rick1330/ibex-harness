package main

import (
	"flag"
	"fmt"
	"os"

	pgmigrate "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
)

func main() {
	command := flag.String("command", "", "migration command: up, down, version")
	flag.Parse()

	if *command == "" && flag.NArg() > 0 {
		*command = flag.Arg(0)
	}
	if *command == "" {
		fmt.Fprintln(os.Stderr, "usage: migrate -command up|down|version")
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
	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n", *command)
		os.Exit(2)
	}
}
